import logging
from typing import *

from artiq.coredevice.adf5356 import ADF5356
from artiq.coredevice.core import Core
from artiq.coredevice.mirny import Mirny
from artiq.experiment import delay
from artiq.experiment import kernel
from ndscan.experiment import ExpFragment
from ndscan.experiment.entry_point import make_fragment_scan_exp
from ndscan.experiment.parameters import BoolParam
from ndscan.experiment.parameters import BoolParamHandle
from ndscan.experiment.parameters import FloatParam
from ndscan.experiment.parameters import FloatParamHandle

from repository.lib.constants import MIRNY_SETTINGS_87
from repository.lib.constants import MIRNY_SETTINGS_88

logger = logging.getLogger(__name__)


class SetEOMSidebandsFrag(ExpFragment):
    """
    Set all the EOM frequencies for using Sr88 / Sr87
    """

    def build_fragment(self):
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
        for settings in MIRNY_SETTINGS_87:
            handle = self.setattr_param(
                f"attenuation_{settings.device_name}",
                FloatParam,
                f"Attenuation for channel {settings.device_name}",
                default=settings.attenuation,
                min=0,
            )
            self.attenuation_handles.append(handle)

    def host_setup(self):
        super().host_setup()

        self.mirny_settings = (
            MIRNY_SETTINGS_87 if self.sr87.get() else MIRNY_SETTINGS_88
        )

        self.mirny_channels: List[ADF5356] = []
        self.mirnys = set()

        for settings in self.mirny_settings:
            channel = self.get_device(settings.device_name)
            self.mirny_channels.append(channel)
            self.mirnys.add(channel.cpld)

        self.mirnys: List[Mirny] = list(self.mirnys)

    @kernel
    def run_once(self) -> None:
        for mirny_cpld in self.mirnys:
            logger.info("Initiating mirny %s", mirny_cpld)
            self.core.break_realtime()
            mirny_cpld.init()

        for i in range(len(self.mirny_channels)):
            mirny_channel = self.mirny_channels[i]
            mirny_settings = self.mirny_settings[i]

            attenuation_handle = self.attenuation_handles[i]
            attenuation = attenuation_handle.get()

            logger.info(
                "Setting mirny %s to %s with %f dB attenuation",
                mirny_channel,
                mirny_settings,
                attenuation,
            )
            self.core.break_realtime()

            mirny_channel.init()

            # Disable the output momentarily to avoid sending the wrong settings
            # at any point
            mirny_channel.sw.set_o(False)
            mirny_channel.set_frequency(mirny_settings.frequency)
            mirny_channel.set_att(attenuation)
            mirny_channel.sw.set_o(mirny_settings.rf_switch)


SetEOMSidebands = make_fragment_scan_exp(SetEOMSidebandsFrag)
