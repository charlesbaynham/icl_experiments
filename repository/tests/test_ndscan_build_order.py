import logging
import time

import numpy as np
from artiq.coredevice.core import Core
from artiq.coredevice.sampler import Sampler
from artiq.coredevice.suservo import SUServo
from artiq.experiment import BooleanValue
from artiq.experiment import delay
from artiq.experiment import EnumerationValue
from artiq.experiment import kernel
from artiq.experiment import ms
from artiq.experiment import NumberValue
from artiq.experiment import rpc
from artiq.experiment import TFloat
from artiq.experiment import us
from koheron_ctl200_laser_driver import CTL200
from ndscan.experiment import BoolParam
from ndscan.experiment import ExpFragment
from ndscan.experiment import FloatParam
from ndscan.experiment import ResultChannel
from ndscan.experiment.entry_point import make_fragment_scan_exp
from ndscan.experiment.parameters import BoolParamHandle
from ndscan.experiment.parameters import FloatParamHandle
from ndscan.experiment.parameters import IntParam
from ndscan.experiment.parameters import IntParamHandle
from ndscan.experiment.parameters import StringParam
from ndscan.experiment.parameters import StringParamHandle
from pyaion.fragments.suservo import LibSetSUServoStatic
from pyaion.lib.utils import get_local_devices

from repository.lib import constants
from repository.lib.fragments.read_adc import ReadADC
from repository.lib.fragments.read_adc import ReadSamplerADC
from repository.lib.fragments.read_adc import ReadSUServoADC


logger = logging.getLogger(__name__)


class TestBuild(ExpFragment):
    def build_fragment(self):
        self.setattr_param("testparam", FloatParam, description="A test", default=123.0)

        print(self.testparam)
        print(self.testparam.get())

    def run_once(self) -> None:
        return


TestBuildExp = make_fragment_scan_exp(TestBuild)
