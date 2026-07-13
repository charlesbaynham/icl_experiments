import logging

import numpy as np
from artiq.coredevice.core import Core
from artiq.coredevice.grabber import GrabberTimeoutException
from artiq.experiment import NumberValue
from artiq.language import delay
from artiq.language import kernel
from artiq.language import portable
from ndscan.experiment import ExpFragment
from ndscan.experiment import make_fragment_scan_exp
from pyaion.fragments.andor_camera import AndorCameraConfig
from pyaion.fragments.andor_camera import AndorCameraControl
from pyaion.models import AndorHardware

logger = logging.getLogger(__name__)

_ANDOR_HW = AndorHardware(
    grabber_device="grabber0",
    camera_device="andor_camera",
    ttl_trigger_device="ttl_camera_trigger_andor",
    ttl_shutter_device="ttl_shutter_andor",
    shutter_open_time=130e-3,
)


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

        n_rois_local = self.N_ROIs
        height_local = self.height

        class _StackedROITestConfig(AndorCameraConfig):
            num_andor_images = 1
            num_images_per_series = 1
            num_grabber_readouts = 1
            num_grabber_rois = n_rois_local

            def build_fragment(self):
                super().build_fragment()
                self.roi_buffer = np.zeros((n_rois_local, 4), dtype=np.int32)
                for i in range(n_rois_local):
                    self.roi_buffer[i][0] = 0
                    self.roi_buffer[i][1] = i * height_local
                    self.roi_buffer[i][2] = 512
                    self.roi_buffer[i][3] = (i + 1) * height_local

            @portable
            def get_rois(self):
                return self.roi_buffer

        self.setattr_fragment("andor_camera_config", _StackedROITestConfig)
        self.andor_camera_config: _StackedROITestConfig

        self.setattr_fragment(
            "andor_camera_control",
            AndorCameraControl,
            camera_config=self.andor_camera_config,
            hardware=_ANDOR_HW,
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
