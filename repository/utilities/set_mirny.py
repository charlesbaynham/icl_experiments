import logging

from artiq.coredevice.adf5356 import ADF5356
from artiq.coredevice.core import Core
from artiq.coredevice.mirny import Mirny
from artiq.experiment import kernel
from artiq.experiment import TFloat
from ndscan.experiment import Fragment
from ndscan.experiment.parameters import BoolParam
from ndscan.experiment.parameters import BoolParamHandle
from ndscan.experiment.parameters import FloatParam
from ndscan.experiment.parameters import FloatParamHandle

import repository.lib.constants as constants


logger = logging.getLogger(__name__)


class TurnOn1379AOM(Fragment):

    """
    Turn on the 1379 AOMs
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

    def host_setup(self):
        super().host_setup()

        self.mirny_channel_1379: ADF5356 = self.get_device("aom_1379")
        self.mirny_689: Mirny = self.mirny_channel_1379.cpld

        self._init_completed = False

    @kernel
    def device_setup(self):
        self.device_setup_subfragments()

        self.core.break_realtime()

        if not self._init_completed:
            self.mirny_channel_1379.init()
            self.mirny_channel_1379.init()

            self._init_completed = True

        # Immediately turn on the output.
        # Do this every time to ensure that any previous offsets are undone
        self.mirny_channel_689.set_att(self.attenuation.get())
        self.offset_1379(0.0)
        self.mirny_channel_1379.sw.set_o(self.rf_sw.get())

    @kernel
    def offset_689(self, offset: TFloat):
        """Offset the 689 frequency relative to its default position

        Args:
            offset (TFloat): Offset from default position
        """
        freq = self.frequency.get()
        self.mirny_channel_1379.set_frequency(freq)
