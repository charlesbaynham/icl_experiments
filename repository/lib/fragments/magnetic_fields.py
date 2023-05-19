import logging

from artiq.coredevice.core import Core
from artiq.experiment import kernel
from artiq.experiment import TFloat
from ndscan.experiment import Fragment

from device_db_config import get_configuration_from_db
from repository.lib.fragments.current_supply_setter import SetAnalogCurrentSupplies
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

        self.setattr_fragment(
            "current_setter_bias",
            SetAnalogCurrentSupplies,
            current_configs=[
                current_config_x,
                current_config_y,
                current_config_z,
            ],
        )
        self.current_setter_bias: SetAnalogCurrentSupplies

        self.setattr_fragment(
            "current_setter_mot",
            SetAnalogCurrentSupply,
            current_config=current_config_mot,
        )
        self.current_setter_mot: SetAnalogCurrentSupply

    @kernel
    def set_bias_fields(self, current_x, current_y, current_z):
        """
        Sets the bias field currents

        Requires at least 3924ns of slack, in which time the Zotino cannot be
        written to by other methods.
        """

        self.current_setter_bias.set_currents([current_x, current_y, current_z])

    @kernel
    def set_mot_gradient(self, current: TFloat):
        """
        Sets the chamber 2 field gradient current
        """
        self.current_setter_mot.set_current(current)
