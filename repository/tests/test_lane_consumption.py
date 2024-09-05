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

    @kernel
    def run(self):
        logger.info("Starting test")

        self.core.break_realtime()
        self.dds.sw.off()  # Safety first
        self.core.break_realtime()

        t_now_mu = now_mu()

        for i in range(self.num):
            at_mu(t_now_mu)
            f = 100e6 + float(i)
            self.dds.set(frequency=f, phase=0.0, amplitude=0.0)

        logger.info("Test done")
