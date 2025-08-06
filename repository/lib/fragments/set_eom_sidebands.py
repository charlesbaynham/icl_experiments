import logging
from typing import List

from artiq.coredevice.adf5356 import ADF5356
from artiq.coredevice.core import Core
from artiq.coredevice.mirny import Mirny
from artiq.language import kernel
from ndscan.experiment import ExpFragment
from ndscan.experiment import Fragment
from ndscan.experiment.parameters import BoolParam
from ndscan.experiment.parameters import BoolParamHandle
from ndscan.experiment.parameters import FloatParam
from ndscan.experiment.parameters import FloatParamHandle

from repository.lib import constants
from repository.lib.constants import MIRNY_SETTINGS_87
from repository.lib.constants import MIRNY_SETTINGS_88
from repository.lib.constants import MirnySettings

logger = logging.getLogger(__name__)


class SetEOMSidebandsFrag(Fragment):
    """
    Set all the EOM frequencies for using Sr88 vs Sr87

    If built with `init_mirnys = False` then don't initiate the Mirnys and
    assume that they're already set up.
    """

    mirny_settings_87: List[MirnySettings] = None
    mirny_settings_88: List[MirnySettings] = None

    def build_fragment(self, init_mirnys=True):
        self.init_mirnys = init_mirnys

        if self.mirny_settings_87 is None or self.mirny_settings_88 is None:
            raise TypeError(
                "You must subclass this class and provide mirny_settings_87 and mirny_settings_88"
            )

        if len(self.mirny_settings_87) != len(self.mirny_settings_88):
            raise TypeError(
                "The length of mirny_settings_87 and mirny_settings_88 must be the same"
            )

        for a, b in zip(self.mirny_settings_87, self.mirny_settings_88):
            if a.device_name != b.device_name:
                raise TypeError("The mirny settings must appear in the same order")

        self.index_of_stir_beam = 0
        for i, settings in enumerate(self.mirny_settings_87):
            if settings.device_name == "mirny_eom_689_sideband":
                self.index_of_stir_beam = i

        if self.index_of_stir_beam is None:
            raise ValueError("The stir beam must be in the list of mirny settings")

        self.setattr_device("core")
        self.core: Core

        self.setattr_param(
            "sr87",
            BoolParam,
            "True = sr87, false = sr88",
            default=constants.USE_SR87,  # TODO: make sure this gets set properly
        )
        self.sr87: BoolParamHandle

        self.attenuation_handles: List[FloatParamHandle] = []
        self.frequency_handles: List[FloatParamHandle] = []

        for settings in self.mirny_settings_87:
            handle_attenuation = self.setattr_param(
                f"attenuation_{settings.device_name}",
                FloatParam,
                f"{settings.device_name} attenuation (-1 = default)",
                default=-1,
                min=-1,
            )
            self.attenuation_handles.append(handle_attenuation)

            handle_frequency = self.setattr_param(
                f"frequency_{settings.device_name}",
                FloatParam,
                f"{settings.device_name} frequency (-1 = default)",
                default=-1,
                min=-1,
                unit="MHz",
            )
            self.frequency_handles.append(handle_frequency)

            self.debug_mode = logger.isEnabledFor(logging.DEBUG)

            self.kernel_invariants = getattr(self, "kernel_invariants", set()) | {
                "debug_mode",
                "index_of_stir_beam",
                "init_mirnys",
                "mirny_settings",
                "mirnys",
                "mirny_channels",
            }

    def host_setup(self):
        super().host_setup()

        self.mirny_settings = (
            self.mirny_settings_87 if self.sr87.get() else self.mirny_settings_88
        )

        self.mirny_channels: List[ADF5356] = []
        self.mirnys = set()

        logger.debug("Preparing EOM sidebands with sr87 = %s", self.sr87.get())

        for settings in self.mirny_settings:
            channel = self.get_device(settings.device_name)
            self.mirny_channels.append(channel)
            self.mirnys.add(channel.cpld)

            logger.debug("Added channel %s", settings.device_name)

        self.mirnys: List[Mirny] = list(self.mirnys)

        self.first_run = True

    @kernel
    def device_setup(self) -> None:
        self.device_setup_subfragments()

        if self.init_mirnys and self.first_run:
            self.first_run = False

            self.core.break_realtime()

            for mirny_cpld in self.mirnys:
                mirny_cpld.init()

            for i in range(len(self.mirny_channels)):
                mirny_channel = self.mirny_channels[i]
                mirny_channel.sync()
                mirny_channel.init()

    @kernel
    def set_sidebands(self):
        for i in range(len(self.mirny_channels)):
            mirny_channel = self.mirny_channels[i]
            mirny_settings = self.mirny_settings[i]

            attenuation_handle = self.attenuation_handles[i]

            attenuation = attenuation_handle.get()
            if attenuation < 0:
                attenuation = mirny_settings.attenuation

            frequency_handle = self.frequency_handles[i]
            frequency = frequency_handle.get()
            if frequency < 0:
                frequency = mirny_settings.frequency

            if self.debug_mode:
                logger.info(
                    "Setting freq=%.3f MHz, att=%f for %s",
                    frequency,
                    attenuation,
                    mirny_settings.device_name,
                )
                self.core.break_realtime()

            # Disable the output momentarily to avoid sending the wrong settings
            # at any point
            mirny_channel.sw.set_o(False)
            mirny_channel.set_frequency(frequency)
            mirny_channel.set_att(attenuation)
            mirny_channel.sw.set_o(mirny_settings.rf_switch)

    @kernel
    def set_689_stir_sideband_detuning(self, detuning: float):
        """
        Set the 689 stir sideband detuning

        Advances the timeline by the duration of SPI writes
        """
        nominal_frequency = self.frequency_handles[self.index_of_stir_beam].get()
        if nominal_frequency < 0:
            nominal_frequency = self.mirny_settings[self.index_of_stir_beam].frequency

        self.mirny_channels[self.index_of_stir_beam].set_frequency(
            nominal_frequency + detuning
        )
        print(nominal_frequency + detuning)

    @kernel
    def set_689_stir_sideband_attenuation(self, attenuation: float):
        """
        Set the 689 stir sideband amplitude

        Advances the timeline by the duration of SPI writes
        """
        self.mirny_channels[self.index_of_stir_beam].set_att(attenuation)


class SetAllEOMSidebandsFrag(SetEOMSidebandsFrag, ExpFragment):
    mirny_settings_87 = MIRNY_SETTINGS_87
    mirny_settings_88 = MIRNY_SETTINGS_88

    @kernel
    def run_once(self):
        self.core.break_realtime()
        self.set_sidebands()


class SetEOMSidebandsExceptCavity(SetEOMSidebandsFrag):
    mirny_settings_87 = [
        s for s in MIRNY_SETTINGS_87 if "cavity_offset" not in s.device_name
    ]
    mirny_settings_88 = [
        s for s in MIRNY_SETTINGS_88 if "cavity_offset" not in s.device_name
    ]
