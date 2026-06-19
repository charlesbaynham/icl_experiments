import time

from artiq.experiment import EnvExperiment

from repository.lib.test import this_str


class TestEcho(EnvExperiment):
    def build(self):
        pass

    def run(self):
        print("Hello, I'm an experiment!")
        print(this_str)

        time.sleep(3)
