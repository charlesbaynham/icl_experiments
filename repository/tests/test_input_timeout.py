from artiq.coredevice.rtio import rtio_input_timestamped_data
from artiq.experiment import *


class InputTimeout(EnvExperiment):
    def build(self):
        self.setattr_device("core")

    @kernel
    def run(self):
        self.core.reset()

        timeout_mu = 100
        channel = 0

        # This should timeout since there's no input
        timestamp, data = rtio_input_timestamped_data(timeout_mu, channel)

        print(timestamp)
        print(data)
