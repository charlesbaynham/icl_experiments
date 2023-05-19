import logging

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

from device_db_config import get_configuration_from_db
from device_db_config.configuration import VoltageControlledCurrentSupply
from repository.lib.fragments.current_supply_setter import SetAnalogCurrentSupply

logger = logging.getLogger(__name__)


class SetMagneticFields(Fragment):
    """
    Set magnetic fields and field gradients
    """

    def build_fragment(self):
        self.setattr_device("core")
        self.core: Core

        current_config_x = get_configuration_from_db("chamber_2_coil_x")
        current_config_y = get_configuration_from_db("chamber_2_coil_y")
        current_config_z = get_configuration_from_db("chamber_2_coil_z")
        current_config_mot = get_configuration_from_db("chamber_2_coil_mot")

        self.current_setter_x = self.setattr_fragment(
            "current_setter_x", SetAnalogCurrentSupply, current_config=current_config_x
        )
        self.current_setter_y = self.setattr_fragment(
            "current_setter_y", SetAnalogCurrentSupply, current_config=current_config_y
        )
        self.current_setter_z = self.setattr_fragment(
            "current_setter_z", SetAnalogCurrentSupply, current_config=current_config_z
        )
        self.current_setter_mot = self.setattr_fragment(
            "current_setter_mot",
            SetAnalogCurrentSupply,
            current_config=current_config_mot,
        )

    @kernel
    def set_bias_fields(self, current_x, current_y, current_z):
        """
        Set a current in amps.
        This method does not advance the timeline.
        """
        voltage = current / self.current_config.gain

        logger.debug(
            "Setting current = %.2f with voltage = %.3f on channel %i",
            current,
            voltage,
            self.current_config.zotino_channel,
        )
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
