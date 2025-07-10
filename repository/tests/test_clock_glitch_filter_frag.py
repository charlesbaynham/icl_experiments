from artiq.coredevice.core import Core
from artiq.language import delay
from artiq.language import kernel
from artiq.language import now_mu
from artiq.language import rpc
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
        print("AA...")

        self.count_glitches()

        print("A...")

        self.core.break_realtime()

        print("B...")

        self.core.wait_until_mu(now_mu())

        print("C...")

        self.start_counting_glitches()

        print("D...")

        delay(2.0)
        self.core.wait_until_mu(now_mu())

        print("E...")

        self.stop_counting_glitches()

        print("F...")

        self.count_glitches()

        print("End!")

    @rpc
    def start_counting_glitches(self):
        print("Started counting glitches.")
        self.clock_glitch_filter.start_counting_glitches()

    @rpc
    def stop_counting_glitches(self):
        self.clock_glitch_filter.stop_counting_glitches()
        print("Stopped counting glitches.")

    @rpc(flags={"async"})
    def count_glitches(self):
        num_glitches = self.clock_glitch_filter.get_num_glitches()
        print(f"Number of glitches counted: {num_glitches}")


TestClockGlitchFilterExp = make_fragment_scan_exp(
    TestClockGlitchFilter,
)
