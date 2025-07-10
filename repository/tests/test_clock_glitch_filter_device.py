from artiq.coredevice.core import Core
from artiq.language import kernel
from ndscan.experiment import ExpFragment
from ndscan.experiment import make_fragment_scan_exp

from repository.lib.devices.clock_glitch_filter import ClockGlitchFilter


class TestClockGlitchFilterDevice(ExpFragment):

    def build_fragment(self):
        self.setattr_device("core")
        self.core: Core

        self.setattr_device("clock_glitch_filter")
        self.clock_glitch_filter: ClockGlitchFilter

    @kernel
    def run_once(self):
        print(self.clock_glitch_filter.get_identity())


TestClockGlitchFilterDeviceExp = make_fragment_scan_exp(
    TestClockGlitchFilterDevice,
)
