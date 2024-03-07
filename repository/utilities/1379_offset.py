import logging

from artiq.coredevice.adf5356 import ADF5356
from artiq.coredevice.core import Core
from artiq.coredevice.mirny import Mirny
from artiq.experiment import kernel
from ndscan.experiment import ExpFragment
from ndscan.experiment.entry_point import make_fragment_scan_exp
from ndscan.experiment.parameters import BoolParam
from ndscan.experiment.parameters import BoolParamHandle
from ndscan.experiment.parameters import FloatParam
from ndscan.experiment.parameters import FloatParamHandle


logger = logging.getLogger(__name__)


class Offset1379Frag(ExpFragment):
    """
    Set offset on 1379
    """

    def build_fragment(self):
        self.setattr_device("core")
        self.core: Core

        self.setattr_param(
            "frequency",
            FloatParam,
            "Static frequency of the Mirny channel",
            unit="MHz",
            default=80e6,
            step=1,
        )

        self.setattr_param(
            "attenuation",
            FloatParam,
            "Attenuation on Mirny output",
            unit="dB",
            default=30,
        )

        self.setattr_param(
            "rf_sw",
            BoolParam,
            "RF switch state",
            default="True",
        )

        self.setattr_param(
            "initiate_mirny",
            BoolParam,
            "Call mirny.init()",
            default="True",
        )

        self.initiate_mirny: BoolParamHandle

        self.attenuation: FloatParamHandle

    def host_setup(self):
        super().host_setup()

        self.mirny_channel_1379_offset: ADF5356 = self.get_device("mirny1_ch0")
        self.mirny_1379_offset: Mirny = self.mirny_channel_1379_offset.cpld

        self._init_completed = False

    @kernel
    def device_setup(self):
        self.device_setup_subfragments()

        self.core.break_realtime()

        if not self._init_completed and self.initiate_mirny.get():
            self.mirny_1379_offset.init()
            self.mirny_channel_1379_offset.init()

            self._init_completed = True

    @kernel
    def run_once(self) -> None:
        self.core.break_realtime()

        self.mirny_channel_1379_offset.set_frequency(self.frequency.get())
        self.mirny_channel_1379_offset.set_att(self.attenuation.get())
        self.mirny_channel_1379_offset.sw.set_o(self.rf_sw.get())


Offset1379 = make_fragment_scan_exp(Offset1379Frag)
