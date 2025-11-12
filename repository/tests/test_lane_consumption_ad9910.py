import logging

from artiq.coredevice.ad9910 import AD9910
from artiq.coredevice.core import Core
from artiq.coredevice.ttl import TTLOut
from artiq.experiment import *
from artiq.language import delay
from ndscan.experiment import ExpFragment
from ndscan.experiment.entry_point import make_fragment_scan_exp

from repository.lib import constants
from repository.lib.fragments.beams.glitchfree_urukul_default_attenuation import (
    GlitchFreeUrukulDefaultAttenuation,
)
from repository.lib.fragments.clock_opll_controller import ClockOPLLController

logger = logging.getLogger(__name__)

# Hypothesis: the AD9910 code is consuming more than one lane in the latest
# ARTIQ update. That's a regression.

# Conclusion: this was not the case. The AD9910 was being perfectly polite in
# its lane usage. The problem was that an ARTIQ update had enabled spread_events
# for DRTIO satellites, breaking our ramping sequences.


class TestAD9910LaneUsage(EnvExperiment):
    def build(self):
        self.setattr_device("core")
        self.core: Core

        self.setattr_argument(
            "num", NumberValue(default=9, type="int", precision=0, scale=1, step=1)
        )
        self.num: int

        self.setattr_argument("urukul_channel", StringValue(default="urukul8_ch2"))

        self.dds: AD9910 = self.get_device(self.urukul_channel)

        self.setattr_device("ttl1")  # This is currently unused and is on the master
        self.ttl: TTLOut = self.ttl1

    @kernel
    def run(self):
        logger.info("Starting test")

        self.core.reset()

        self.dds.sw.off()  # Safety first

        delay(500e3)  # Make loads of slack

        # Do an AD9910 write, consuming at least one lane, maybe more
        self.dds.set(frequency=100e6)

        for i in range(self.num):
            # Write in backwards order to ensure that we use a new lane each time
            delay(-1e-3)
            self.ttl.set_o(bool(i % 2))
            print(i)

        logger.info("Test done")


class TestAD9910RamperLaneUsage(ExpFragment):
    def build_fragment(self):
        self.setattr_device("core")
        self.core: Core

        self.setattr_argument(
            "num", NumberValue(default=9, type="int", precision=0, scale=1, step=1)
        )
        self.num: int

        self.setattr_fragment("clock_opll", ClockOPLLController)
        self.clock_opll: ClockOPLLController

        self.setattr_device("ttl1")  # This is currently unused and is on the master
        self.ttl: TTLOut = self.ttl1

        # Init of the clock OPLL without glitching
        self.setattr_fragment(
            "GlitchFreeUrukulClock",
            GlitchFreeUrukulDefaultAttenuation,
            constants.URUKULED_BEAMS["698_clock_OPLL_offset"].urukul_device,
            constants.URUKULED_BEAMS["698_clock_OPLL_offset"].attenuation,
        )

    @kernel
    def run_once(self):
        logger.info("Starting test")

        self.core.reset()

        delay(5.0)  # Make loads of slack

        # Do an AD9910 write, consuming at least one lane, maybe more
        # self.clock_opll.clock_frequency_ramper.stop_ramp()
        # self.clock_opll.clock_OPLL_offset.set(80e6)
        # self.clock_opll.clock_frequency_ramper.start_ramp(10.0, 80e6, 80.01e6, 1)

        for i in range(self.num):
            # Write in backwards order to ensure that we use a new lane each time
            delay(-1e-3)
            self.ttl.set_o(bool(i % 2))
            print(i)

        logger.info("Test done")


TestAD9910LaneUsageExp = make_fragment_scan_exp(TestAD9910RamperLaneUsage)
