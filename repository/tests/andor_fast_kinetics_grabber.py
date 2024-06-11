import logging

from artiq.experiment import delay
from artiq.experiment import kernel
from artiq.experiment import NumberValue
from ndscan.experiment import ExpFragment
from ndscan.experiment import make_fragment_scan_exp

from repository.lib.fragments.cameras.andor_camera import AndorCameraControl


logger = logging.getLogger(__name__)


class TestFastKineticsGrabber(ExpFragment):
    def build_fragment(self):
        self.setattr_device("core")

        self.setattr_argument(
            "N", NumberValue(default=5, precision=0, scale=1, step=1, type="int")
        )
        self.setattr_argument(
            "height", NumberValue(default=10, precision=0, scale=1, step=1, type="int")
        )

        if self.N is None:
            self.N = 3

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
                for i in range(self.N)
            ],
            add_pre_trigger_delay=True,
        )
        self.andor_camera_control: AndorCameraControl

    @kernel
    def run_once(self):
        self.core.break_realtime()

        for _ in range(8):
            delay(10e-3)
            self.andor_camera_control.trigger(
                exposure=1e-3,
                control_shutter=False,
            )

        self.save_data()

    @kernel
    def save_data(self):
        # Save Andor data
        sums = [0] * self.N
        means = [0.0] * self.N
        self.andor_camera_control.readout_ROIs(
            sums,
            means,
            self.core.get_rtio_counter_mu() + self.core.seconds_to_mu(1.0),
        )

        for i in range(self.N):
            logger.info("[%d] %f", i, sums[i])


TestFastKineticsGrabber = make_fragment_scan_exp(TestFastKineticsGrabber)
