from artiq.coredevice.core import Core
from artiq.language import delay
from artiq.language import now_mu
from ndscan.experiment import *
from ndscan.experiment.entry_point import make_fragment_scan_exp

from repository.lib import constants
from repository.lib.fragments.beams.glitchfree_urukul_default_attenuation import (
    GlitchFreeUrukulDefaultAttenuation,
)
from repository.lib.fragments.clock_opll_controller import ClockOPLLController


class TestClockRamper(ExpFragment):

    def build_fragment(self):

        self.setattr_device("core")
        self.core: Core

        self.setattr_fragment("clock_opll", ClockOPLLController)
        self.clock_opll: ClockOPLLController

        # Init of the clock OPLL without glitching
        self.setattr_fragment(
            "GlitchFreeUrukulClock",
            GlitchFreeUrukulDefaultAttenuation,
            constants.URUKULED_BEAMS["698_clock_OPLL_offset"].urukul_device,
            constants.URUKULED_BEAMS["698_clock_OPLL_offset"].attenuation,
        )

    @kernel
    def run_once(self):

        start_time = now_mu()

        self.clock_opll.clock_frequency_ramper.start_ramp(1e6, 80e6, 81e6, 1)

        delay(1.0)

        self.clock_opll.clock_frequency_ramper.stop_ramp()

        end_time = now_mu()

        new_freq = 1e6 * self.core.mu_to_seconds(end_time - start_time + 1)

        self.clock_opll.clock_OPLL_offset.set(80e6 + new_freq)

        delay(1.0)


TestClockRamperExp = make_fragment_scan_exp(TestClockRamper)
