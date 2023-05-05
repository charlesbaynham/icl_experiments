from artiq.coredevice.core import Core
from artiq.experiment import delay
from artiq.experiment import now_mu
from ndscan.experiment import ExpFragment
from ndscan.experiment import kernel
from ndscan.experiment.entry_point import make_fragment_scan_exp

from repository.lib.fragments.blue_3d_mot import Blue3DMOTFrag


class TestBlue3DMOTPushBeamFrag(ExpFragment):
    def build_fragment(self) -> None:
        self.setattr_device("core")
        self.core: Core

        self.setattr_fragment("frag_blue_3d_mot", Blue3DMOTFrag)
        self.frag_blue_3d_mot: Blue3DMOTFrag

    @kernel
    def device_setup(self) -> None:
        self.core.reset()
        self.device_setup_subfragments()

    @kernel
    def run_once(self):
        self.core.break_realtime()
        self.frag_blue_3d_mot.enable_mot_beams()

        for _ in range(10):
            delay(1.0)
            self.frag_blue_3d_mot.turn_on_3d_mot_beams()
            delay(1.0)
            self.frag_blue_3d_mot.turn_on_push_beam()
            delay(1.0)
            self.frag_blue_3d_mot.turn_off_3d_mot_beams()
            delay(1.0)
            self.frag_blue_3d_mot.turn_off_push_beam()

        self.core.wait_until_mu(now_mu())


TestBlue3DMOTPushBeam = make_fragment_scan_exp(TestBlue3DMOTPushBeamFrag)
