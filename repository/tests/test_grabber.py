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

    @kernel
    def run(self):
        self.core.reset()

        # Setup grabber ROI 0
        self.grabber0.setup_roi(0, 138, 148, 263, 350)

        delay(1.0)

        # Turn grabber ROI 0 on
        self.grabber0.gate_roi(0x01)

        # get data
        data = [0]
        self.grabber0.input_mu(data)

        # Disable the ROI again
        self.core.break_realtime()
        self.grabber0.gate_roi(0x00)

        self.core.reset()
        print(data)
