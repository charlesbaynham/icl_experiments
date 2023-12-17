from artiq.coredevice.core import Core
from artiq.experiment import *
from ndscan.experiment import ExpFragment
from ndscan.experiment import FloatParam
from ndscan.experiment.entry_point import make_fragment_scan_exp

from repository.lib.fragments.andor_camera import AndorCameraControl


class MultipleGrabs(ExpFragment):
    def build_fragment(self, *args, **kwargs) -> None:
        self.setattr_device("core")
        self.core: Core

        self.setattr_fragment("andor_interface", AndorCameraControl)
        self.andor_interface: AndorCameraControl

        self.setattr_param("delay", FloatParam, default=10e-3)

    def run_once(self) -> None:
        self.core.break_realtime()

        self.andor_interface.trigger()
        delay(self.delay.get())
        self.andor_interface.trigger()

        sums = [0, 0]
        means = [0.0, 0.0]
        self.andor_interface.readout_images(
            sums, means, timeout_mu=now_mu() + self.core.seconds_to_mu(1.0)
        )

        print(sums)
        print(means)


MultipleGrabs = make_fragment_scan_exp(MultipleGrabs)
