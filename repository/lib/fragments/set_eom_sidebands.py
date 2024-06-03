import logging
from typing import *
from typing import List

from artiq.coredevice.adf5356 import ADF5356
from artiq.coredevice.core import Core
from artiq.coredevice.mirny import Mirny
from artiq.experiment import kernel
from ndscan.experiment import ExpFragment
from ndscan.experiment import Fragment
from ndscan.experiment.parameters import BoolParam
from ndscan.experiment.parameters import BoolParamHandle
from ndscan.experiment.parameters import FloatParam
from ndscan.experiment.parameters import FloatParamHandle

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

        self.setattr_device("core")
        self.core: Core

        self.setattr_param(
            "sr87",
            BoolParam,
            "True = sr87, false = sr88",
            default=False,
        )
        self.sr87: BoolParamHandle

        self.attenuation_handles: List[FloatParamHandle] = []

        for settings in self.mirny_settings_87:
            handle_attenuation = self.setattr_param(
                f"attenuation_{settings.device_name}",
                FloatParam,
                f"Attenuation for channel {settings.device_name}",
                default=settings.attenuation,
                min=0,
            )
            self.attenuation_handles.append(handle_attenuation)

    def host_setup(self):
        super().host_setup()

        self.mirny_settings = (
            self.mirny_settings_87 if self.sr87.get() else self.mirny_settings_88
        )

        self.mirny_channels: List[ADF5356] = []
        self.mirnys = set()

        for settings in self.mirny_settings:
            channel = self.get_device(settings.device_name)
            self.mirny_channels.append(channel)
            self.mirnys.add(channel.cpld)

        self.mirnys: List[Mirny] = list(self.mirnys)

        logger.debug("Preparing EOM sidebands with sr87 = %s", self.sr87.get())

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
                mirny_channel.init()

    @kernel
    def set_sidebands(self):
        for i in range(len(self.mirny_channels)):
            mirny_channel = self.mirny_channels[i]
            mirny_settings = self.mirny_settings[i]

            attenuation_handle = self.attenuation_handles[i]
            attenuation = attenuation_handle.get()

            frequency = self.mirny_settings[i].frequency

            # Disable the output momentarily to avoid sending the wrong settings
            # at any point
            mirny_channel.sw.set_o(False)
            mirny_channel.set_frequency(frequency)
            mirny_channel.set_att(attenuation)
            mirny_channel.sw.set_o(mirny_settings.rf_switch)


class SetAllEOMSidebandsFrag(SetEOMSidebandsFrag, ExpFragment):
    mirny_settings_87 = MIRNY_SETTINGS_87
    mirny_settings_88 = MIRNY_SETTINGS_88

    @kernel
    def run_once(self):
        self.core.break_realtime()
        self.set_sidebands()
