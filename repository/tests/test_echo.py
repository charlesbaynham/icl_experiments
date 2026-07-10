import time

from artiq.coredevice.core import Core
from artiq.experiment import EnvExperiment
from artiq.language import kernel

from repository.lib.test import this_str


class TestEcho(EnvExperiment):
    def build(self):
        self.setattr_device("core")
        self.core: Core

    def run(self):
        print("Hello, I'm an experiment!")
        print(this_str)

        self.kernel()

        time.sleep(3)

    @kernel
    def kernel(self):
        print("Hello from the kernel!")
        print(this_str)
