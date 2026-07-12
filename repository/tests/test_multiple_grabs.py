import numpy as np
from artiq.coredevice.core import Core
from artiq.experiment import *
from artiq.language import portable
from ndscan.experiment import FloatParam
from ndscan.experiment import *
from ndscan.experiment.entry_point import make_fragment_scan_exp
from ndscan.experiment.parameters import IntParamHandle
from pyaion.fragments.andor_camera import AndorCameraConfig
from pyaion.fragments.andor_camera import AndorCameraControl
from pyaion.models import AndorHardware

_ANDOR_HW = AndorHardware(
    grabber_device="grabber0",
    camera_device="andor_camera",
    ttl_trigger_device="ttl_camera_trigger_andor",
    ttl_shutter_device="ttl_shutter_andor",
    shutter_open_time=130e-3,
)


class _DummySingleROIConfig(AndorCameraConfig):
    num_andor_images = 1
    num_images_per_series = 1
    num_grabber_readouts = 1
    num_grabber_rois = 1

    def build_fragment(self):
        super().build_fragment()
        self.roi_buffer = np.array([[0, 0, 1, 1]], dtype=np.int32)

    @portable
    def get_rois(self):
        return self.roi_buffer


class MultipleGrabs(ExpFragment):
    def build_fragment(self, *args, **kwargs) -> None:
        self.setattr_device("core")
        self.core: Core

        self.setattr_fragment("andor_camera_config", _DummySingleROIConfig)
        self.andor_camera_config: _DummySingleROIConfig

        self.setattr_fragment(
            "andor_interface",
            AndorCameraControl,
            camera_config=self.andor_camera_config,
            hardware=_ANDOR_HW,
        )
        self.andor_interface: AndorCameraControl

        self.setattr_param(
            "delay",
            FloatParam,
            default=10e-3,
            description="Delay between images",
            unit="ms",
        )

        self.setattr_param(
            "num_triggers", IntParam, default=2, description="Num triggers"
        )
        self.num_triggers: IntParamHandle

        self.setattr_param("num_reads", IntParam, default=2, description="Num reads")
        self.num_reads: IntParamHandle

    @kernel
    def run_once(self) -> None:
        self.core.break_realtime()

        delay(1.0)

        for _ in range(self.num_triggers.get()):
            self.andor_interface.trigger(exposure=1e-6, control_shutter=False)
            delay(self.delay.get())

        sums = [0] * self.num_reads.get()
        means = [0.0] * self.num_reads.get()
        self.andor_interface.readout_ROIs(
            sums,
            means,
            timeout_mu=now_mu() + self.core.seconds_to_mu(1.0),
        )

        print(sums)
        print(means)


MultipleGrabs = make_fragment_scan_exp(MultipleGrabs)
