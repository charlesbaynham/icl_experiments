from artiq.coredevice.core import Core
from artiq.language import delay
from artiq.language import kernel
from artiq.language import now_mu
from artiq.language import rpc
from ndscan.experiment import ExpFragment
from ndscan.experiment import FloatChannel
from ndscan.experiment import FloatParam
from ndscan.experiment import make_fragment_scan_exp
from ndscan.experiment.parameters import FloatParamHandle

from repository.lib.experiment_templates.mixins.clock_glitch_counting import (
    ClockGlitchFilterFrag,
)


class TestClockGlitchFilter(ExpFragment):

    def build_fragment(self):
        self.setattr_device("core")
        self.core: Core

        self.setattr_fragment("clock_glitch_filter", ClockGlitchFilterFrag)
        self.clock_glitch_filter: ClockGlitchFilterFrag

        self.setattr_param(
            "count_time", FloatParam, description="Time to count", unit="s", default=2
        )
        self.count_time: FloatParamHandle

        self.setattr_result("num_glitches")
        self.num_glitches: FloatChannel

    @kernel
    def run_once(self):
        self.core.break_realtime()

        self.start_counting_glitches()

        delay(self.count_time.get())
        self.stop_counting_glitches()

        delay(0.1)
        self.core.wait_until_mu(now_mu())
        self.count_glitches()

    @kernel
    def start_counting_glitches(self):
        self.clock_glitch_filter.start_counting_glitches()

    @kernel
    def stop_counting_glitches(self):
        self.clock_glitch_filter.stop_counting_glitches()

    @rpc(flags={"async"})
    def count_glitches(self):
        num_glitches = self.clock_glitch_filter.get_num_glitches()
        print(f"Number of glitches counted: {num_glitches}")

        self.num_glitches.push(num_glitches)


TestClockGlitchFilterExp = make_fragment_scan_exp(
    TestClockGlitchFilter,
)
