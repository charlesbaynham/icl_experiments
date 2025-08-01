import logging

from artiq.coredevice.ad9910 import AD9910
from artiq.coredevice.core import Core
from artiq.experiment import EnumerationValue
from artiq.experiment import NumberValue
from artiq.language import delay
from artiq.language import kernel
from ndscan.experiment import ExpFragment
from ndscan.experiment.entry_point import make_fragment_scan_exp
from pyaion.fragments.ad9910_ramper import AD9910Ramper
from pyaion.lib.utils import get_local_devices

logger = logging.getLogger(__name__)


class TestAD9910RamperFrag(ExpFragment):
    def build_fragment(self):
        self.setattr_device("core")
        self.core: Core

        ad9910_channels = get_local_devices(self, AD9910)
        if not ad9910_channels:
            raise ValueError("No AD9910 channels found in device_db")
        self.setattr_argument(
            "channel", EnumerationValue(ad9910_channels, default=ad9910_channels[0])
        )

        self.setattr_fragment("ramper", AD9910Ramper, self.channel)
        self.ramper: AD9910Ramper

        self.setattr_argument(
            "f_min", NumberValue(default=10e6, unit="MHz", precision=6)
        )
        self.setattr_argument(
            "f_max", NumberValue(default=20e6, unit="MHz", precision=6)
        )
        self.setattr_argument(
            "df_dt", NumberValue(default=1e6, unit="MHz", precision=6)
        )

        self.setattr_argument(
            "mode",
            EnumerationValue(
                [
                    "Triangle",
                    "Positive saw",
                    "Negative saw",
                ],
                default="Triangle",
            ),
        )

    def host_setup(self):
        super().host_setup()

        modes = {
            "Triangle": 0,
            "Positive saw": 1,
            "Negative saw": 2,
        }

        self.scan_type = modes[self.mode]

    @kernel
    def run_once(self):
        self.core.break_realtime()
        delay(100e-3)

        self.ramper.start_ramp(self.df_dt, self.f_min, self.f_max, self.scan_type)


TestAD9910Ramper = make_fragment_scan_exp(TestAD9910RamperFrag)
