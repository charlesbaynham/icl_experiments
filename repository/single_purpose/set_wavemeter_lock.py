from artiq.experiment import BooleanValue
from artiq.experiment import EnvExperiment
from wand.server import ControlInterface as WandServer


class EnableWavemeterLock(EnvExperiment):
    """
    Enable or disable wavemeter locking with WAND
    """

    def build(self):
        self.setattr_argument("enable", BooleanValue(default=True))
        self.setattr_device("wand_server")
        self.wand_server: WandServer

        self.setattr_argument("include_461", BooleanValue(default=False))

    def run(self):

        for laser in self.wand_server.get_laser_db().keys():
            if self.enable and (laser != "461" or self.include_461):
                self.wand_server.lock(laser, set_point=0.0, timeout=None)
            else:
                self.wand_server.unlock(laser, name="")
