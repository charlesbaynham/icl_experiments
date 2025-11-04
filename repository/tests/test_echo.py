import time

from artiq.experiment import EnvExperiment


class TestEcho(EnvExperiment):
    def build(self):
        pass

    def run(self):
        print("Hello, I'm an experiment!")

        time.sleep(3)
