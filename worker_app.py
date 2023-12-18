from settings import Settings

settings = Settings()

print(f"Starting worker #{settings.worker_id}")

import os
import psutil
import zmq
import msgpack
import numpy as np
import time
from turbojpeg import TurboJPEG, TJPF_RGB
from utils.imutil import imresize

from sfast.compilers.stable_diffusion_pipeline_compiler import (
    compile,
    CompilationConfig,
)

from diffusers.utils.logging import disable_progress_bar
from diffusers import AutoPipelineForImage2Image, AutoencoderTiny
import torch
import warnings

warnings.filterwarnings("ignore", category=torch.jit.TracerWarning)

from PIL import Image

from fixed_seed import fix_seed
from threaded_worker import ThreadedWorker

base_model = "stabilityai/sdxl-turbo"
vae_model = "madebyollin/taesdxl"

disable_progress_bar()
pipe = AutoPipelineForImage2Image.from_pretrained(
    base_model,
    torch_dtype=torch.float16,
    variant="fp16",
    local_files_only=settings.local_files_only,
)

pipe.vae = AutoencoderTiny.from_pretrained(
    vae_model, torch_dtype=torch.float16, local_files_only=settings.local_files_only
)
fix_seed(pipe)

print("Model loaded")

config = CompilationConfig.Default()
config.enable_xformers = True
config.enable_triton = True
config.enable_cuda_graph = True
pipe = compile(pipe, config=config)

print("Model compiled")

pipe.to(device="cuda", dtype=torch.float16).to("cuda")
pipe.set_progress_bar_config(disable=True)

print("Model moved to GPU", flush=True)


class WorkerReceiver(ThreadedWorker):
    def __init__(self, hostname, port):
        super().__init__(has_input=False)
        self.context = zmq.Context()
        self.sock = self.context.socket(zmq.PULL)
        self.sock.setsockopt(zmq.RCVTIMEO, 100)
        self.sock.setsockopt(zmq.RCVHWM, 1)
        self.sock.setsockopt(zmq.LINGER, 0)
        address = f"tcp://{hostname}:{port}"
        print(f"WorkerReceiver connecting to {address}")
        self.sock.connect(address)
        self.jpeg = TurboJPEG()

    def work(self):
        while not self.should_exit:
            try:
                msg = self.sock.recv(flags=zmq.NOBLOCK, copy=False).bytes
                receive_time = time.time()
                # print(int(time.time()*1000)%1000, "receiving")
            except zmq.Again:
                continue
            unpacked = msgpack.unpackb(msg)
            # print("incoming length", len(msg))
            
            # print("receiving", unpacked["indices"])
            
            # oldest_timestamp = min(unpacked["timestamps"])
            # latency = time.time() - oldest_timestamp
            # if latency > 0.5:
                # print(f"{int(latency)}ms dropping old frames")
                # continue
            # print(f"{int(latency)}ms received {unpacked['indices']}")
            
            parameters = unpacked["parameters"]
            images = []
            for frame in unpacked["frames"]:
                img = self.jpeg.decode(frame, pixel_format=TJPF_RGB)
                images.append(img / 255)
            unpacked["frames"] = images
            return unpacked

    def cleanup(self):
        self.sock.close()
        self.context.term()


class Processor(ThreadedWorker):
    def __init__(self):
        super().__init__()
        self.generator = None
        self.batch_count = 0

    def diffusion(self, images, parameters):
        # print("images", len(images), images[0].shape)
        return pipe(
            prompt=[parameters["prompt"]] * len(images),
            image=images,
            generator=self.generator,
            num_inference_steps=parameters["num_inference_steps"],
            guidance_scale=0,
            strength=parameters["strength"],
            output_type="np",
        ).images

    def work(self, unpacked):
        start_time = time.time()

        images = unpacked["frames"]
        parameters = unpacked["parameters"]

        if parameters["passthrough"]:
            results = images
        else:
            if parameters["fixed_seed"] or self.generator is None:
                self.generator = torch.manual_seed(parameters["seed"])
            results = self.diffusion(images, parameters)

        unpacked["frames"] = results

        if self.batch_count % 10 == 0:
            latency = time.time() - unpacked["job_timestamp"]
            duration = time.time() - start_time
            print(
                f"diffusion {int(duration*1000)}ms latency {int(latency*1000)}ms",
                flush=True,
            )
        self.batch_count += 1
        
        return unpacked


class WorkerSender(ThreadedWorker):
    def __init__(self, hostname, port):
        super().__init__(has_output=False)
        self.context = zmq.Context()
        self.sock = self.context.socket(zmq.PUSH)
        self.sock.setsockopt(zmq.SNDHWM, 1)
        self.sock.setsockopt(zmq.LINGER, 0)
        address = f"tcp://{hostname}:{port}"
        print(f"WorkerSender connecting to {address}")
        self.sock.connect(address)
        self.jpeg = TurboJPEG()

    def work(self, unpacked):
        indices = unpacked["indices"]
        results = unpacked["frames"]
        job_timestamp = unpacked["job_timestamp"]

        msgs = []
        for index, result in zip(indices, results):
            img_u8 = (result * 255).astype(np.uint8)
            jpg = self.jpeg.encode(img_u8, pixel_format=TJPF_RGB)
            msg = msgpack.packb(
                {
                    "job_timestamp": job_timestamp,
                    "index": index,
                    "jpg": jpg,
                    "worker_id": settings.worker_id,
                }
            )
            msgs.append(msg)
            
        for index, msg in zip(indices, msgs):
            self.sock.send(msg)
        
    def cleanup(self):
        print("WorkerSender push close")
        self.sock.close()
        print("WorkerSender context term")
        self.context.term()


# create from beginning to end
receiver = WorkerReceiver(settings.primary_hostname, settings.job_start_port)
processor = Processor().feed(receiver)
sender = WorkerSender(settings.primary_hostname, settings.job_finish_port).feed(processor)

# warmup
if settings.warmup:
    warmup_shape = [settings.batch_size, *map(int, settings.warmup.split("x"))]
    shape_str = "x".join(map(str, warmup_shape))
    images = np.zeros(warmup_shape, dtype=np.float32)
    for i in range(2):
        print(f"Warmup {shape_str} {i+1}/2")
        start_time = time.time()
        processor.diffusion(
            images, {"prompt": "warmup", "num_inference_steps": 2, "strength": 1.0}
        )
    print("Warmup finished", flush=True)

# start from end to beginning
sender.start()
processor.start()
receiver.start()

try:
    process = psutil.Process(os.getpid())
    while True:
        memory_usage_bytes = process.memory_info().rss
        memory_usage_gb = memory_usage_bytes / (1024**3)
        if memory_usage_gb > 10:
            print(f"memory usage: {memory_usage_gb:.2f}GB")
        time.sleep(1)
except KeyboardInterrupt:
    pass

# close end to beginning
sender.close()
processor.close()
receiver.close()
