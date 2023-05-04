from artiq.coredevice.core import Core
from artiq.experiment import delay
from ndscan.experiment import ExpFragment
from ndscan.experiment import kernel

from repository.lib.fragments.blue_3d_mot import Blue3DMOTFrag


class TestBlue3DMOTPushBeam(ExpFragment):
    def build_fragment(self) -> None:
        self.setattr_device("core")
        self.core: Core

        self.setattr_fragment("frag_blue_3d_mot", Blue3DMOTFrag)
        self.frag_blue_3d_mot: Blue3DMOTFrag

    @kernel
    def run_once(self):
        self.core.break_realtime()
        self.frag_blue_3d_mot.enable_mot()

        for _ in range(10):
            delay(1.0)
            self.frag_blue_3d_mot.push_beam_off()
            delay(1.0)
            self.frag_blue_3d_mot.push_beam_on()
