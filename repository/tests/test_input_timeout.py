import numpy as np
from artiq.coredevice.rtio import rtio_input_timestamped_data
from artiq.experiment import *


class InputTimeout(EnvExperiment):
    def build(self):
        self.setattr_device("core")

        self.setattr_argument(
            "channel", NumberValue(default=0, precision=0, scale=1, step=1)
        )
        self.setattr_argument(
            "timeout_mu", NumberValue(default=100, precision=0, scale=1, step=1)
        )

    @kernel
    def run(self):
        self.core.reset()

        # This should timeout since there's no input
        timestamp, data = rtio_input_timestamped_data(
            np.int64(self.timeout_mu), self.channel
        )

        print(timestamp)
        print(data)
