from artiq.coredevice.core import Core
from artiq.coredevice.sampler import Sampler
from artiq.experiment import EnvExperiment
from artiq.experiment import kernel


class TestDemo(EnvExperiment):
    def build(self):
        self.setattr_device("core")
        self.core: Core

        self.setattr_device("sampler2")
        self.sampler2: Sampler

    @kernel
    def run(self):
        self.core.reset()

        ###

        self.sampler2.init()

        samples = [0.0] * 8
        self.sampler2.sample(samples)

        print(samples)
