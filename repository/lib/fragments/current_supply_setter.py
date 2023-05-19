import logging
from typing import Optional

from artiq.coredevice.core import Core
from artiq.coredevice.zotino import Zotino
from artiq.experiment import delay
from artiq.experiment import EnumerationValue
from artiq.experiment import kernel
from ndscan.experiment import ExpFragment
from ndscan.experiment import FloatParam
from ndscan.experiment import Fragment
from ndscan.experiment.entry_point import make_fragment_scan_exp
from ndscan.experiment.parameters import FloatParamHandle

from device_db_config import get_all_configurations_from_db
from device_db_config.configuration import VoltageControlledCurrentSupply

logger = logging.getLogger(__name__)


class SetAnalogCurrentSupply(Fragment):
    """
    Set a current supply that's controlled by an analog voltage
    """

    def build_fragment(self, current_config: VoltageControlledCurrentSupply):
        self.setattr_device("core")
        self.core: Core

        self.current_config = current_config

        self.zotino = self.get_device(self.current_config.zotino)
        self.zotino: Zotino

    @kernel
    def device_setup(self) -> None:
        self.core.break_realtime()
        self.zotino.init()
        delay(200e-6)
        self.zotino.set_dac([0.0] * 32)

        self.device_setup_subfragments()

    @kernel
    def set_current(self, current):
        """
        Set a current in amps.
        This method does not advance the timeline.
        """
        voltage = current / self.current_config.gain

        logger.debug("Setting current = %.2f with voltage = %.3f", current, voltage)
        self.zotino.set_dac([voltage], [self.current_config.zotino_channel])


class SetAnalogCurrentSupplyExpFrag(ExpFragment):
    def build_fragment(self):
        self.setattr_device("core")
        self.core: Core

        current_configs = {
            k: v
            for k, v in get_all_configurations_from_db().items()
            if isinstance(v, VoltageControlledCurrentSupply)
        }

        self.setattr_argument(
            "current_supply", EnumerationValue(list(current_configs.keys()))
        )
        self.current_supply: str

        if self.current_supply is not None:
            current_config = current_configs[self.current_supply]

        else:
            current_config = list(current_configs.values())[0]

        self.setattr_fragment("setter", SetAnalogCurrentSupply, current_config)
        self.setter: SetAnalogCurrentSupply

        self.setattr_param(
            "current", FloatParam, "Current to set", default=0.0, unit="A"
        )
        self.current: FloatParamHandle

    @kernel
    def run_once(self):
        self.core.break_realtime()
        delay(10e-3)
        self.setter.set_current(self.current.get())


SetAnalogCurrentSupplyExp = make_fragment_scan_exp(SetAnalogCurrentSupplyExpFrag)
