from threaded_worker import ThreadedWorker
from osc_socket import OscSocket

class OscSettingsController(ThreadedWorker):
    def __init__(self, settings, host, port):
        super().__init__(has_input=False, has_output=False)
        self.osc = OscSocket(host, port)
        self.settings = settings
        
    def work(self):
        msg = self.osc.recv()
        if msg is None:
            return
        if msg.address == "/prompt":
            prompt = ' '.join(msg.params)
            print("OSC prompt:", prompt)
            self.settings.settings["prompt"] = prompt
        elif msg.address == "/seed":
            seed = msg.params[0]
            print("OSC seed:", seed)
            self.settings.settings["seed"] = seed
        else:
            print("unknown osc", msg.address, msg.params)
            
    def cleanup(self):
        self.osc.close()