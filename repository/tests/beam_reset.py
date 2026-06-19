from ndscan.experiment import ExpFragment
from ndscan.experiment import kernel
from ndscan.experiment import make_fragment_scan_exp

from repository.lib.fragments.beams.reset_all_beams import ResetAllICLBeams


class ResetBeamsFrag(ExpFragment):
    def build_fragment(self):
        self.setattr_device("core")
        self.setattr_fragment("reset", ResetAllICLBeams)

    @kernel
    def run_once(self) -> None:
        print("Running...")


ResetBeams = make_fragment_scan_exp(ResetBeamsFrag)
