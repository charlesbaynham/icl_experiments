from artiq.experiment import BooleanValue
from artiq.experiment import EnvExperiment
from wand.server import ControlInterface as WandServer

LASERS = ["461", "689", "689_IJD", "707", "679"]


class EnableWavemeterLock(EnvExperiment):
    """
    Enable or disable wavemeter locking with WAND
    """

    def build(self):
        self.setattr_device("wand_server")
        self.wand_server: WandServer

        for laser in LASERS:
            self.setattr_argument(laser, BooleanValue(default=True))

    def run(self):

        for laser in LASERS:
            laser_enabled = getattr(self, laser)

            if laser_enabled:
                self.wand_server.lock(laser, set_point=0.0, timeout=None)
            else:
                self.wand_server.unlock(laser, name="")
