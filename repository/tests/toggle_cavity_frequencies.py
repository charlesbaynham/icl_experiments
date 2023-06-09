from artiq.coredevice.core import Core
from artiq.experiment import delay
from artiq.experiment import kernel
from artiq.experiment import now_mu
from ndscan.experiment import ExpFragment
from ndscan.experiment import FloatParam
from ndscan.experiment.entry_point import make_fragment_scan_exp

from repository.lib.fragments.cavity_control import LaserStabilisationSystem


class ToggleCavityFreqs(ExpFragment):
    def build_fragment(self, *args, **kwargs) -> None:
        self.setattr_device("core")
        self.core: Core
        self.setattr_fragment("laser_stab", LaserStabilisationSystem)
        self.laser_stab: LaserStabilisationSystem

        self.setattr_param("stepsize", FloatParam, "Step size", default=1e3, unit="Hz")

    @kernel
    def run_once(self) -> None:
        self.core.break_realtime()

        self.laser_stab.offset_689(0.0)
        delay(1.0)
        self.laser_stab.offset_689(self.stepsize.get())
        delay(1.0)


ToggleCavityFreqs = make_fragment_scan_exp(ToggleCavityFreqs)
