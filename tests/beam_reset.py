from ndscan.experiment import *

from repository.lib.fragments.beams.reset_all_beams import ResetAllICLBeams


class ResetBeams(ExpFragment):
    def build_fragment(self):
        self.setattr_device("core")
        self.setattr_fragment("reset", ResetAllICLBeams)

    @kernel
    def run_once(self) -> None:
        print("Running...")
