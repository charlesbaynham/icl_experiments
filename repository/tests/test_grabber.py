from artiq.coredevice.core import Core
from artiq.coredevice.grabber import Grabber
from artiq.experiment import *
from artiq.experiment import delay
from artiq.language import MHz
from artiq.language import ms
from artiq.language import ns
from artiq.language import us


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

        self.setattr_argument(
            "roi_x1", NumberValue(default=1, precision=0, scale=1, step=1)
        )
        self.setattr_argument(
            "roi_x2", NumberValue(default=1, precision=0, scale=1, step=1)
        )
        self.setattr_argument(
            "roi_y1", NumberValue(default=1, precision=0, scale=1, step=1)
        )
        self.setattr_argument(
            "roi_y2", NumberValue(default=1, precision=0, scale=1, step=1)
        )

    @kernel
    def run(self):
        self.core.reset()

        # Setup all grabber ROIs
        for i in range(0, 16):
            self.grabber0.setup_roi(
                i, self.roi_x1, self.roi_y1, self.roi_x2, self.roi_y2
            )

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


class FrameGrabberExample(EnvExperiment):
    """
    Copied from https://github.com/m-labs/artiq/issues/1369
    """

    def build(self):
        self.setattr_device("core")
        self.setattr_device("grabber0")
        self.setattr_device("ttl_camera_trigger_andor")

    @kernel
    def run(self):
        rois = [[227, 237, 237, 247], [247, 237, 257, 247]]
        mask = 0
        self.core.reset()
        for i in range(len(rois)):
            x0 = rois[i][0]
            y0 = rois[i][1]
            x1 = rois[i][2]
            y1 = rois[i][3]
            mask |= 1 << i
            self.grabber0.setup_roi(i, x0, y0, x1, y1)
        n = [0] * len(rois)

        self.ttl_camera_trigger_andor.pulse(10 * us)  # camera trigger
        delay(20 * ms)
        self.grabber0.gate_roi(mask)
        self.ttl_camera_trigger_andor.pulse(10 * us)  # camera trigger

        self.grabber0.input_mu(n)

        self.core.break_realtime()
        self.grabber0.gate_roi(0)

        print("ROI sums:", n)
        print("ROI mask:", mask)
