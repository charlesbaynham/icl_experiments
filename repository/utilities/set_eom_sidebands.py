import logging

from artiq.coredevice.adf5356 import ADF5356
from artiq.coredevice.core import Core
from artiq.coredevice.mirny import Mirny
from artiq.experiment import EnumerationValue
from artiq.experiment import kernel
from ndscan.experiment import ExpFragment
from ndscan.experiment.entry_point import make_fragment_scan_exp
from ndscan.experiment.parameters import BoolParam
from ndscan.experiment.parameters import BoolParamHandle
from ndscan.experiment.parameters import FloatParam
from ndscan.experiment.parameters import FloatParamHandle
from pyaion.lib.utils import get_local_devices

from repository.lib.constants import MIRNY_SETTINGS_87
from repository.lib.constants import MIRNY_SETTINGS_88

logger = logging.getLogger(__name__)


class SetEOMSidebands(ExpFragment):
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

    def host_setup(self):
        super().host_setup()

        self.mirny_settings = (
            MIRNY_SETTINGS_87 if self.sr87.get() else MIRNY_SETTINGS_88
        )

        self.mirny_channels = []
        self.mirnys = set()

        for settings in self.mirny_settings:
            channel = self.get_device(settings.device_name)
            self.mirny_channels.append(channel)
            self.mirnys.add(channel.cpld)

        self.mirnys = list(self.mirnys)

    @kernel
    def device_setup(self):
        self.device_setup_subfragments()

        self.core.break_realtime()

        for mirny_cpld in self.mirnys:
            mirny_cpld.init()

        for mirny_channel in self.mirny_channels:
            mirny_channel.init()

    @kernel
    def run_once(self) -> None:
        self.core.break_realtime()

        self.mirny_channel.set_frequency(self.frequency.get())
        self.mirny_channel.set_att(self.attenuation.get())
        self.mirny_channel.sw.set_o(self.rf_sw.get())


SetMirny = make_fragment_scan_exp(SetMirnyFrag)
