import logging

from artiq.coredevice.core import Core
from artiq.coredevice.grabber import GrabberTimeoutException
from artiq.experiment import NumberValue
from artiq.language import delay
from artiq.language import kernel
from ndscan.experiment import ExpFragment
from ndscan.experiment import make_fragment_scan_exp

from repository.lib.fragments.cameras.andor_camera import AndorCameraControl

logger = logging.getLogger(__name__)


class TestFastKineticsGrabber(ExpFragment):
    def build_fragment(self):
        self.setattr_device("core")
        self.core: Core

        self.setattr_argument(
            "N_ROIs", NumberValue(default=5, precision=0, scale=1, step=1, type="int")
        )
        self.setattr_argument(
            "N_triggers",
            NumberValue(default=5, precision=0, scale=1, step=1, type="int"),
        )

        self.setattr_argument(
            "height", NumberValue(default=10, precision=0, scale=1, step=1, type="int")
        )

        if self.N_ROIs is None:
            self.N_ROIs = 3

        if self.height is None:
            self.height = 10

        # Nx ROIs
        self.setattr_fragment(
            "andor_camera_control",
            AndorCameraControl,
            roi_defaults=[
                [
                    0,
                    i * self.height,
                    512,
                    (i + 1) * self.height,
                ]
                for i in range(self.N_ROIs)
            ],
            add_pre_trigger_delay=True,
        )
        self.andor_camera_control: AndorCameraControl

    @kernel
    def run_once(self):
        self.core.break_realtime()

        # self.core.wait_until_mu(now_mu())
        # self.core.reset()

        for _ in range(self.N_triggers):
            delay(10e-3)
            self.andor_camera_control.trigger(
                exposure=1e-3,
                control_shutter=False,
            )

        self.save_data()

    @kernel
    def save_data(self):
        # Try to read out until we get a timeout error

        loop = 0
        while True:
            try:
                # Save Andor data
                sums = [0] * self.N_ROIs
                means = [0.0] * self.N_ROIs
                self.andor_camera_control.readout_ROIs(
                    sums,
                    means,
                    self.core.get_rtio_counter_mu() + self.core.seconds_to_mu(1.0),
                )

                logger.info("Loop = %d", loop)
                for i in range(self.N_ROIs):
                    logger.info("[%d] %f", i, sums[i])

                loop += 1
            except GrabberTimeoutException:
                logger.info("loop = %d was the last", loop)
                break


TestFastKineticsGrabber = make_fragment_scan_exp(TestFastKineticsGrabber)
