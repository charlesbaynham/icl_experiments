from artiq.experiment import BooleanValue
from artiq.experiment import EnvExperiment
from wand.server import ControlInterface as WandServer


class EnableWavemeterLock(EnvExperiment):
    """
    Enable / disable wavemeter locking with WAND
    """

    def build(self):
        self.setattr_argument("enable", BooleanValue(default=True))
        self.setattr_device("wand_server")
        self.wand_server: WandServer

    def run(self):
        for laser in self.wand_server.get_laser_db().keys():
            self.wand_server.lock(laser, set_point=0.0, timeout=None)
