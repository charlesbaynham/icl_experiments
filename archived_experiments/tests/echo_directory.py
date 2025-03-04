from artiq.experiment import *


class EchoEnvironment(EnvExperiment):
    def build(self):
        pass

    def run(self):
        import os
        import sys

        ppath = "\n".join(sys.path)

        print(f"sys.path = {ppath}")
        print(f"os.getcwd() = {os.getcwd()}")
