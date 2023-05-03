import logging
import re
import time

import numpy as np
from artiq.coredevice.core import Core
from artiq.coredevice.sampler import Sampler
from artiq.coredevice.suservo import Channel
from artiq.coredevice.suservo import Channel as SUServoChannel
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

from repository.lib.fragments.read_adc import ReadSUServoADC

logger = logging.getLogger(__name__)


class DisplaySUServoMonitorsFrag(ExpFragment):
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

        suservo_channel_names = {
            "suservo_aom_doublepass_461_injection": "suservo1_ch3",
            "suservo_aom_singlepass_461_spectroscopy": "suservo1_ch7",
            "suservo_aom_singlepass_461_pushbeam": "suservo1_ch2",
            "suservo_aom_singlepass_461_2dmot_a": "suservo1_ch0",
            "suservo_aom_singlepass_461_2dmot_b": "suservo1_ch1",
            "suservo_aom_singlepass_461_3DMOT_radial": "suservo1_ch4",
            "suservo_aom_singlepass_461_3DMOT_axialplus": "suservo1_ch5",
            "suservo_aom_singlepass_461_3DMOT_axialminus": "suservo1_ch6",
        }
        self.setattr_argument(
            "suservo_channel_name", EnumerationValue(list(suservo_channel_names.keys()))
        )
        self.suservo: SUServo = self.get_device("suservo1")
        self.suservo_channel = int(
            re.match(
                r"suservo\d+_ch(\d+)", suservo_channel_names[self.suservo_channel_name]
            )[1]
            if self.suservo_channel_name is not None
            else 0
        )

        # Define result channels as outputs
        self.setattr_result("voltage")
        self.voltage: ResultChannel

        # Get SUServo reader fragment
        self.setattr_fragment(
            "adc_reader", ReadSUServoADC, self.suservo, self.suservo_channel
        )
        self.adc_reader: ReadSUServoADC

    @kernel
    def device_setup(self) -> None:
        self.device_setup_subfragments()
        delay(10 * ms)

    @kernel
    def run_once(self):
        delay(self.waittime.get())

        v = self.adc_reader.read_adc()

        self.voltage.push(v)


DisplaySUServoMonitors = make_fragment_scan_exp(DisplaySUServoMonitorsFrag)
