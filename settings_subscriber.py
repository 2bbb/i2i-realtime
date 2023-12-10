import threading
import uvicorn
from fastapi import FastAPI
import time

from safety_checker import SafetyChecker
from translate import Translate

class SettingsSubscriber:
    def __init__(self, port):
        self.shutdown = False
        self.settings = {
            "fixed_seed": True,
            "seed": 0,
            "num_inference_steps": 2,
            "guidance_scale": 0.0,
            "strength": 0.7,
            "size": 1024,
            "prompt": "A man playing piano."
        }
        self.thread = threading.Thread(target=self.run, args=(port,))
        self.thread.start()
        
    def __getitem__(self, key):
        return self.settings[key]

    def run(self, port):
        safety_checker = SafetyChecker()
        translate = Translate()

        app = FastAPI()

        @app.get("/prompt/{msg}")
        async def prompt(msg: str):
            prompt = translate.translate_to_en(msg)
            if prompt != msg:
                print("Translating from:", msg)
            if safety_checker(prompt) == "unsafe":
                print("Ignoring unsafe prompt:", prompt)
                return {"safety": "unsafe"}
            else:
                self.settings["prompt"] = prompt
                print("Updated prompt:", prompt)
                return {"safety": "safe"}

        @app.get("/fixed_seed/{status}")
        async def fixed_seed(status: bool):
            self.settings["fixed_seed"] = status
            print("Updated fixed_seed status:", self.settings["fixed_seed"])
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

        @app.get("/size/{value}")
        async def size(value: int):
            self.settings["size"] = value
            print("Updated size:", self.settings["size"])
            return {"status": "updated"}

        config = uvicorn.Config(app, host="127.0.0.1", port=port, log_level="info")
        self.server = uvicorn.Server(config=config)
        try:
            self.server.run()
        except KeyboardInterrupt:
            pass
            
    def close(self):
        if hasattr(self, 'server'):
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