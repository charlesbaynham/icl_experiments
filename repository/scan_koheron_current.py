import logging

from artiq.coredevice.core import Core
from artiq.coredevice.sampler import Sampler
from artiq.coredevice.suservo import Channel
from artiq.coredevice.suservo import SUServo
from artiq.coredevice.urukul import CPLD
from artiq.experiment import EnumerationValue
from artiq.experiment import kernel
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
from pyaion.lib.utils import get_local_devices

from repository.lib.fragments.read_suservo_adc import ReadSUServoADC

logger = logging.getLogger(__name__)


class ScanKoheronCurrentFrag(ExpFragment):
    """
    Set a Koheron CTL200 laser driver's current and measure an analog input in response
    """

    def build_fragment(self):
        self.setattr_device("core")
        self.core: Core

        self.setattr_param(
            "current",
            FloatParam,
            description="Current to set",
            default=0,
            min=0,
            max=400,
            unit="mA",
            step=0.1,
        )
        self.current: FloatParamHandle

        # Choose the controller to set:
        controller_names = [
            k
            for k, v in self.get_device_db().items()
            if (
                ("type" in v and v["type"] == "controller")
                and (
                    "command" in v
                    and "aqctl_koheron_ctl200_laser_driver" in v["command"]
                )
            )
        ]
        if not controller_names:
            raise ValueError("No CTL200 Koheron controllers found in device_db")
        self.setattr_argument("controller_name", EnumerationValue(controller_names))
        self.controller: CTL200 = self.get_device(self.controller_name)

        # And the suservo channel to read
        suservos = get_local_devices(self, SUServo)
        if not suservos:
            raise ValueError("No suservo devices found in device_db")
        self.setattr_argument("suservo_device", EnumerationValue(suservos))
        self.setattr_argument(
            "suservo_channel",
            NumberValue(
                default=0, ndecimals=0, scale=1, step=1, min=0, max=7, type="int"
            ),
        )
        self.suservo_channel: int
        self.suservo_device: str

        self.print_debug_statements = logger.isEnabledFor(logging.DEBUG)

        # # Load the sampler utility from pyaion
        # self.setattr_fragment("sampler_reader", SamplerReader)
        # self.sampler_reader: SamplerReader

        self.setattr_fragment(
            "suservo_reader", ReadSUServoADC, self.suservo_device, self.suservo_channel
        )
        self.suservo_reader: ReadSUServoADC

        # And define a results channel as output
        self.setattr_result("voltage")
        self.voltage: ResultChannel

    @kernel
    def run_once(self):
        cur = self.current.get()
        self.set_current(cur)
        voltage = self.suservo_reader.read_adc()
        self.voltage.push(voltage)

    @rpc
    def set_current(self, current):
        self.controller.set_current_mA(current)


ScanKoheronCurrent = make_fragment_scan_exp(ScanKoheronCurrentFrag)
