import logging
import re

from artiq.coredevice.core import Core
from artiq.coredevice.suservo import SUServo
from artiq.experiment import delay
from artiq.experiment import EnumerationValue
from artiq.experiment import kernel
from artiq.experiment import ms
from ndscan.experiment import ExpFragment
from ndscan.experiment import FloatParam
from ndscan.experiment import ResultChannel
from ndscan.experiment.entry_point import make_fragment_scan_exp
from ndscan.experiment.parameters import FloatParamHandle

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

        device_db_suservo_aliases = {
            k: v
            for k, v in self.get_device_db().items()
            if "suservo" in k and isinstance(v, str)
        }

        self.setattr_argument(
            "suservo_channel_name",
            EnumerationValue(
                list(device_db_suservo_aliases.keys()),
                default=list(device_db_suservo_aliases.keys())[0],
            ),
        )
        suservo_name = (
            re.match(
                r"(suservo\d+)_ch\d+",
                device_db_suservo_aliases[self.suservo_channel_name],
            )[1]
            if self.suservo_channel_name is not None
            else "suservo0"
        )
        self.suservo: SUServo = self.get_device(suservo_name)
        self.suservo_channel = int(
            re.match(
                r"suservo\d+_ch(\d+)",
                device_db_suservo_aliases[self.suservo_channel_name],
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
