from artiq.coredevice.core import Core
from artiq.coredevice.grabber import Grabber
from artiq.coredevice.grabber import OutOfSyncException
from artiq.coredevice.rtio import rtio_input_data
from artiq.coredevice.rtio import rtio_input_timestamped_data
from artiq.experiment import *
from artiq.experiment import delay
from artiq.language import MHz
from artiq.language import ms
from artiq.language import ns
from artiq.language import us
from ndscan.experiment import ExpFragment
from ndscan.experiment.entry_point import make_fragment_scan_exp
from ndscan.experiment.result_channels import FloatChannel


class TestGrabberTimeout(ExpFragment):
    def build_fragment(self):
        self.setattr_device("core")
        self.core: Core

        self.setattr_device("grabber0")
        self.grabber0: Grabber

        self.setattr_device("ttl_camera_trigger_andor")

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

        self.setattr_result("sum", FloatChannel)
        self.sum: FloatChannel

    @kernel
    def input_timeout_mu(self, grabber, data, timeout_mu: TInt64):
        """
        Retrieves the accumulated values for one frame from the ROI engines.
        Blocks until values are available.

        The input list must be a list of integers of the same length as there
        are enabled ROI engines. This method replaces the elements of the
        input list with the outputs of the enabled ROI engines, sorted by
        number.

        If the number of elements in the list does not match the number of
        ROI engines that produced output, an exception will be raised during
        this call or the next.
        """
        channel = grabber.channel_base + 1

        sentinel = rtio_input_data(channel)
        if sentinel != grabber.sentinel:
            raise OutOfSyncException

        for i in range(len(data)):
            timestamp, roi_output = rtio_input_timestamped_data(timeout_mu, channel)
            if timestamp == -1:
                raise RuntimeError
            if roi_output == grabber.sentinel:
                raise OutOfSyncException
            data[i] = roi_output

    @kernel
    def run_once(self):
        self.core.reset()

        # Setup one grabber ROI
        self.grabber0.setup_roi(0, self.roi_x1, self.roi_y1, self.roi_x2, self.roi_y2)

        delay(10e-6)

        # Turn grabber ROI 0 on
        self.grabber0.gate_roi(0x01)

        # camera trigger
        self.ttl_camera_trigger_andor.pulse(10 * us)

        # get data
        data = [0]
        self.input_timeout_mu(self.grabber0, data, self.core.seconds_to_mu(1.0))

        # Disable the ROI again
        self.core.break_realtime()
        self.grabber0.gate_roi(0x00)

        self.core.reset()

        self.sum.push(data[0])


TestGrabberTimeout = make_fragment_scan_exp(TestGrabberTimeout)
