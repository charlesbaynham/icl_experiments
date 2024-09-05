import logging
from typing import List

from artiq.coredevice.ad9910 import AD9910
from artiq.coredevice.core import Core
from artiq.coredevice.suservo import Channel as SUServoChannel
from artiq.coredevice.ttl import TTLOut
from artiq.experiment import *
from artiq.experiment import at_mu
from artiq.experiment import delay
from artiq.experiment import delay_mu
from artiq.experiment import now_mu
from artiq.experiment import parallel
from artiq.experiment import sequential


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

        self.setattr_device("urukul8_ch2")  # This is currently unused
        self.dds: AD9910 = self.urukul8_ch2

        self.setattr_device("ttl1")  # This is currently unused
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
