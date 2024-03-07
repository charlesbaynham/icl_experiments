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
