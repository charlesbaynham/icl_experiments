import logging

from artiq.coredevice.core import Core
from artiq.coredevice.zotino import Zotino
from artiq.experiment import EnvExperiment
from artiq.experiment import kernel
from artiq.experiment import NumberValue


logger = logging.getLogger(__name__)


class SetZotinoVoltage(EnvExperiment):
    def build(self):
        self.setattr_device("core")
        self.core: Core

        self.setattr_device("zotino_plant_room")
        self.zotino_plant_room: Zotino

        self.setattr_argument(
            "channel", NumberValue(default=0, ndecimals=0, step=1, scale=1, type="int")
        )
        self.setattr_argument("voltage", NumberValue(default=0.0, unit="V"))

    @kernel
    def run(self):
        self.core.reset()
        self.zotino_plant_room.init()
        self.zotino_plant_room.set_dac([self.voltage], [self.channel])
