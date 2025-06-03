from artiq.coredevice.core import Core
from artiq.language import delay
from artiq.language import now_mu
from ndscan.experiment import *

from repository.lib.fragments.red_mot import RedBeamController


class TestRedBeamControllerFrag(ExpFragment):
    def build_fragment(self):
        self.setattr_device("core")
        self.core: Core

        self.setattr_fragment("controller", RedBeamController)
        self.controller: RedBeamController

    @kernel
    def run_once(self) -> None:
        print("Running...")

        self.core.break_realtime()

        self.controller.init()

        self.core.break_realtime()
        delay(100e-3)

        self.controller.turn_on_mot_beams()
        delay(10e-3)
        self.controller.turn_off_mot_beams()
        delay(20e-3)

        self.controller.turn_on_spin_pol()
        delay(10e-3)
        self.controller.turn_off_spin_pol()

        self.core.wait_until_mu(now_mu())
        print("Done")


TestRedBeamController = make_fragment_scan_exp(TestRedBeamControllerFrag)
