from artiq.coredevice.core import Core
from artiq.coredevice.grabber import Grabber
from artiq.experiment import *
from artiq.experiment import delay


class TestGrabber(EnvExperiment):
    def build(self):
        self.setattr_device("core")
        self.core: Core

        self.setattr_device("grabber0")
        self.grabber0: Grabber

        self.setattr_argument(
            "num", NumberValue(default=1, precision=0, scale=1, step=1)
        )
        self.num: int

    @kernel
    def run(self):
        self.core.reset()

        # Setup all grabber ROIs
        for i in range(0, 16):
            self.grabber0.setup_roi(i, 138, 148, 263, 350)

        delay(1.0)

        # Turn grabber ROI 0 on
        self.grabber0.gate_roi(0x01)

        # get data
        data = [0] * self.num
        for i in range(self.num):
            self.grabber0.input_mu(data[i : i + 1])

        # Disable the ROI again
        self.core.break_realtime()
        self.grabber0.gate_roi(0x00)

        self.core.reset()
        for i in range(self.num):
            print(data[i])
