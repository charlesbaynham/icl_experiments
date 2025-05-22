import logging

from artiq.coredevice.core import Core
from artiq.experiment import TFloat
from artiq.language import kernel
from artiq.language import rpc
from ndscan.experiment import Fragment
from ndscan.experiment.parameters import FloatParam
from ndscan.experiment.parameters import FloatParamHandle
from tenma_power_supply import TENMAPowerSupply

from device_db_config import get_configuration_from_db
from repository.lib import constants
from repository.lib.fragments.current_supply_setter import SetAnalogCurrentSupplies

logger = logging.getLogger(__name__)


class SetMagneticFieldsQuick(Fragment):
    """
    Set zotino-controlled magnetic fields and field gradients
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
            SetAnalogCurrentSupplies,
            current_configs=[current_config_mot],
        )
        self.current_setter_mot: SetAnalogCurrentSupplies

        self.setattr_fragment(
            "current_setter_all",
            SetAnalogCurrentSupplies,
            current_configs=[
                current_config_mot,
                current_config_x,
                current_config_y,
                current_config_z,
            ],
        )
        self.current_setter_all: SetAnalogCurrentSupplies

    @kernel
    def set_bias_fields(self, current_x, current_y, current_z):
        """
        Sets the bias field currents

        This method does not advance the timeline but does require at least
        1.5us + 808ns * len(currents) on a Kasli 1.x as SPI events are written
        into the past.
        """

        self.current_setter_bias.set_currents([current_x, current_y, current_z])

    @kernel
    def set_mot_gradient(self, current: TFloat):
        """
        Sets the chamber 2 field gradient current

        This method does not advance the timeline but does require at least
        1.5us + 808ns * len(currents) on a Kasli 1.x as SPI events are written
        into the past.
        """
        self.current_setter_mot.set_currents([current])

    @kernel
    def set_all_fields(self, current_mot, current_x, current_y, current_z):
        """
        Sets both MOT gradient and bias field currents

        This method does not advance the timeline but does require at least
        1.5us + 808ns * len(currents) on a Kasli 1.x as SPI events are written
        into the past.
        """

        self.current_setter_all.set_currents(
            [current_mot, current_x, current_y, current_z]
        )


class SetMagneticFieldsSlow(Fragment):
    """
    Set serial / ethernet magnetic fields and field gradients
    """

    def build_fragment(self):
        self.setattr_device("core")
        self.core: Core

        self.setattr_param(
            "ch1_axial_current",
            FloatParam,
            "Current in ch1 axial coils",
            unit="A",
            min=0,
            max=10,
            default=constants.B_FIELD_CH1_AXIAL,
        )
        self.ch1_axial_current: FloatParamHandle

        # %% Kernel variables
        self.coils_initiated = False
        self.ch1_axial_last_value = 0.0

    def host_setup(self):
        # TODO: this is in host_setup because the __init__ method of the driver
        # creates a connection immediately, i.e. during the "prepare" phase of
        # ARTIQ. This is bad!
        self.setattr_device("chamber_1_axial_coil_driver")
        self.chamber_1_axial_coil_driver: TENMAPowerSupply

        return super().host_setup()

    @kernel
    def device_setup(self) -> None:
        self.device_setup_subfragments()
        self.set_fields_if_required()

    @kernel
    def set_fields_if_required(self):
        """
        Sets fields to their pre-configured static values

        Trys to avoid doing this, since it's slow and requires an RPC
        """
        axial_field = self.ch1_axial_current.get()

        if not self.coils_initiated or self.ch1_axial_last_value != axial_field:
            self.set_ch1_axial(axial_field)
            self.coils_initiated = True
            self.ch1_axial_last_value = axial_field

    @rpc
    def set_ch1_axial(self, current: TFloat):
        self.chamber_1_axial_coil_driver.set_current(current)
