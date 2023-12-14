import threading
import uvicorn
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
import time

from safety_checker import SafetyChecker
from translate import Translate


class SettingsSubscriber:
    def __init__(self, port, use_translation, use_safety_checker):
        self.shutdown = False
        self.settings = {
            "directory": "data/bg",
            "fixed_seed": True,
            "batch_size": 4,
            "seed": 0,
            "resolution": 1024,
            "passthrough": False,
            "num_inference_steps": 2,
            "guidance_scale": 0.0,
            "strength": 0.7,
            "prompt": "A psychedelic landscape."
        }
        self.use_translation = use_translation
        self.use_safety_checker = use_safety_checker
        self.thread = threading.Thread(target=self.run, args=(port,))
        self.thread.start()

    def __getitem__(self, key):
        return self.settings[key]

    def run(self, port):
        if self.use_translation:
            translate = Translate()
        if self.use_safety_checker:
            safety_checker = SafetyChecker()

        app = FastAPI()

        # Add CORS middleware
        app.add_middleware(
            CORSMiddleware,
            allow_origins=["*"],
            allow_methods=["*"],
            allow_headers=["*"],
        )

        @app.get("/prompt/{msg}")
        async def prompt(msg: str):
            if self.use_translation:
                prompt = translate.translate_to_en(msg)
                if prompt != msg:
                    print("Translating from:", msg)
            else:
                prompt = msg
            
            override = "-f" in prompt
            if override:
                prompt = prompt.replace("-f", "").strip()
            if self.use_safety_checker and safety_checker(prompt) == "unsafe":
                print("Ignoring unsafe prompt:", prompt)
                return {"safety": "unsafe"}
            
            self.settings["prompt"] = prompt
            print("Updated prompt:", prompt)
            return {"safety": "safe"}

        @app.get("/passthrough/{status}")
        async def passthrough(status: bool):
            self.settings["passthrough"] = status
            print("Updated passthrough status:", self.settings["passthrough"])
            return {"status": "updated"}

        @app.get("/fixed_seed/{status}")
        async def fixed_seed(status: bool):
            self.settings["fixed_seed"] = status
            print("Updated fixed_seed status:", self.settings["fixed_seed"])
            return {"status": "updated"}

        @app.get("/resolution/{value}")
        async def resolution(value: int):
            self.settings["resolution"] = value
            print("Updated resolution:", self.settings["resolution"])
            return {"status": "updated"}

        @app.get("/batch_size/{value}")
        async def batch_size(value: int):
            self.settings["batch_size"] = value
            print("Updated batch_size:", self.settings["batch_size"])
            return {"status": "updated"}

        @app.get("/seed/{value}")
        async def seed(value: int):
            self.settings["seed"] = value
            print("Updated seed:", self.settings["seed"])
            return {"status": "updated"}

        @app.get("/steps/{value}")
        async def steps(value: int):
            self.settings["num_inference_steps"] = value
            print("Updated num_inference_steps:", self.settings["num_inference_steps"])
            return {"status": "updated"}

        @app.get("/guidance/{value}")
        async def guidance(value: float):
            self.settings["guidance_scale"] = value
            print("Updated guidance_scale:", self.settings["guidance_scale"])
            return {"status": "updated"}

        @app.get("/strength/{value}")
        async def strength(value: float):
            self.settings["strength"] = value
            print("Updated strength:", self.settings["strength"])
            return {"status": "updated"}

        config = uvicorn.Config(app, host="0.0.0.0", port=port, log_level="info")
        self.server = uvicorn.Server(config=config)
        try:
            self.server.run()
        except KeyboardInterrupt:
            pass

    def close(self):
        if hasattr(self, "server"):
            self.server.should_exit = True
        self.thread.join()


if __name__ == "__main__":
    sub = SettingsSubscriber(5556)
    try:
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        pass
    sub.close()
