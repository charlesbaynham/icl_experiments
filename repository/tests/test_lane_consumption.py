import logging

from artiq.coredevice.core import Core
from artiq.experiment import *
from artiq.experiment import delay
from artiq.experiment import delay_mu
from artiq.experiment import now_mu
from artiq.experiment import parallel
from artiq.experiment import sequential

logger = logging.getLogger(__name__)

# Hypothesis: the AD9910 code is consuming more than one lane in the latest ARTIQ update. That's a regression.
# TODO: Write a test here to check this. Use "test_lanes_during_ramps.py" as inspiration.

NUM_LANES = 16


class TestAD9910LaneUsage(EnvExperiment):
    def build(self):
        self.setattr_device("core")
        self.core: Core

        self.ttls = [self.get_device(f"ttl{i}") for i in range(NUM_LANES)]

    @kernel
    def run(self):
        logger.info("Starting test")

        self.core.break_realtime()

        with parallel:
            for ttl in self.ttls:
                ttl.on()

        self.core.wait_until_mu(now_mu())
        logger.info("Test done, resetting TTLs")

        for ttl in self.ttls:
            self.core.break_realtime()
            ttl.off()
