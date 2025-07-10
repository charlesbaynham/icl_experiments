from artiq.coredevice.core import Core
from artiq.experiment import rpc
from artiq.language import delay
from artiq.language import kernel
from artiq.language import now_mu
from ndscan.experiment import ExpFragment
from ndscan.experiment import make_fragment_scan_exp

from repository.lib.experiment_templates.mixins.clock_glitch_counting import (
    ClockGlitchFilterFrag,
)


class TestClockGlitchFilter(ExpFragment):

    def build_fragment(self):
        self.setattr_device("core")
        self.core: Core

        self.setattr_fragment("clock_glitch_filter", ClockGlitchFilterFrag)
        self.clock_glitch_filter: ClockGlitchFilterFrag

    @kernel
    def run_once(self):
        self.count_glitches()

        self.core.break_realtime()
        self.core.wait_until_mu(now_mu())

        self.start_counting_glitches()

        delay(2.0)
        self.core.wait_until_mu(now_mu())

        self.stop_counting_glitches()
        self.count_glitches()

    @rpc
    def start_counting_glitches(self):
        return  # FIXME
        # self.clock_glitch_filter.start_counting_glitches()
        # print("Started counting glitches.")

    @rpc
    def stop_counting_glitches(self):
        return  # FIXME
        # self.clock_glitch_filter.stop_counting_glitches()
        # print("Stopped counting glitches.")

    @rpc(flags={"async"})
    def count_glitches(self):
        return  # FIXME
        # num_glitches = self.clock_glitch_filter.get_num_glitches()
        # print(f"Number of glitches counted: {num_glitches}")


TestClockGlitchFilterExp = make_fragment_scan_exp(
    TestClockGlitchFilter,
)
