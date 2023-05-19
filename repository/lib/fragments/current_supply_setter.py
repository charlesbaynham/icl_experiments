import logging
from typing import Optional

from artiq.coredevice.core import Core
from artiq.coredevice.zotino import Zotino
from artiq.experiment import delay
from artiq.experiment import EnumerationValue
from artiq.experiment import kernel
from ndscan.experiment import Fragment

from device_db_config import get_all_configurations_from_db
from device_db_config.configuration import VoltageControlledCurrentSupply

logger = logging.getLogger(__name__)


class SetAnalogCurrentSupply(Fragment):
    """
    Set a current supply that's controlled by an analog voltage
    """

    def build_fragment(
        self, current_config: Optional[VoltageControlledCurrentSupply] = None
    ):
        self.setattr_device("core")
        self.core: Core

        if current_config is None:
            current_configs = {
                k: v
                for k, v in get_all_configurations_from_db().items()
                if isinstance(v, VoltageControlledCurrentSupply)
            }

            self.setattr_argument(
                "current_supply", EnumerationValue(current_configs.keys())
            )
            self.current_supply: str

            if self.current_supply is not None:
                self.current_config = current_configs[self.current_supply]
        else:
            self.current_config = current_config

        if self.current_config is not None:
            self.zotino = self.get_device(self.current_config.zotino)
            self.zotino: Zotino

    def host_setup(self):
        if self.current_config is None:
            RuntimeError("self.current_config is None")
        return super().host_setup()

    @kernel
    def device_setup(self) -> None:
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
