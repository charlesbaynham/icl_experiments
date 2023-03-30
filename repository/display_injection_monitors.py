import logging
import time

import numpy as np
from artiq.coredevice.core import Core
from artiq.coredevice.sampler import Sampler
from artiq.coredevice.suservo import Channel
from artiq.coredevice.suservo import SUServo
from artiq.coredevice.urukul import CPLD
from artiq.experiment import BooleanValue
from artiq.experiment import delay
from artiq.experiment import EnumerationValue
from artiq.experiment import kernel
from artiq.experiment import ms
from artiq.experiment import NumberValue
from artiq.experiment import rpc
from artiq.experiment import RTIOUnderflow
from artiq.experiment import TFloat
from koheron_ctl200_laser_driver import CTL200
from ndscan.experiment import ExpFragment
from ndscan.experiment import FloatParam
from ndscan.experiment import ResultChannel
from ndscan.experiment.entry_point import make_fragment_scan_exp
from ndscan.experiment.parameters import FloatParamHandle
from ndscan.experiment.parameters import IntParam
from ndscan.experiment.parameters import IntParamHandle
from pyaion.lib.utils import get_local_devices

from repository.lib import constants
from repository.lib.fragments.read_adc import ReadADC
from repository.lib.fragments.read_adc import ReadSamplerADC
from repository.lib.fragments.read_adc import ReadSUServoADC

logger = logging.getLogger(__name__)


class DisplayInjectionMonitors(ExpFragment):
    def build_fragment(self):
        self.setattr_device("core")
        self.core: Core

        self.setattr_param(
            "waittime",
            FloatParam,
            description="Time between measurements",
            default=0.1,
            min=0,
            max=1000,
            unit="s",
            step=0.01,
        )
        self.waittime: FloatParamHandle

        self.sampler: Sampler = self.get_device("sampler_IJD_monitor")

        # self.sampler_channel_names = [
        #     "sampler_channel_IJD1",
        #     "sampler_channel_IJD2",
        #     "sampler_channel_IJD3",
        # ]
        # self.sampler_channels = [
        #     self.get_device_db()[k] for k in self.sampler_channel_names
        # ]
        self.sampler_channels = [0, 1, 2]  # hard-code for now

        # Define result channels as outputs
        self.setattr_result("v_IJD1")
        self.setattr_result("v_IJD2")
        self.setattr_result("v_IJD3")
        self.voltage: ResultChannel

    @kernel
    def device_setup(self) -> None:
        self.device_setup_subfragments()
        self.core.break_realtime()
        delay(1 * ms)
        self.sampler.init()

    @kernel
    def run_once(self):
        samples = [0.0] * 8

        delay(self.waittime.get())

        self.sampler.sample(samples)

        self.v_IJD1.push(self.sampler_channels[0])
        self.v_IJD2.push(self.sampler_channels[1])
        self.v_IJD3.push(self.sampler_channels[2])


DisplayInjectionMonitors = make_fragment_scan_exp(DisplayInjectionMonitors)
