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

# Hypothesis: the AD9910 code is consuming more than one lane in the latest ARTIQ update. That's a regression.
# TODO: Write a test here to check this. Use "test_lanes_during_ramps.py" as inspiration.


class TestAD9910LaneUsage(EnvExperiment):
    def build(self):
        self.setattr_device("core")
        self.core: Core

        # self.urukul_channels: List[AD9910] = [
        #     self.get_device(f"urukul5_ch{i}") for i in range(4)
        # ] + [self.get_device(f"urukul8_ch{i}") for i in range(4)]

        # self.setattr_device("ttl0")
        # self.ttl0: TTLOut

        # for uc in self.urukul_channels:
        #     print(uc)

        self.setattr_device("urukul5_ch0")
        self.urukul5_ch0: AD9910

    @kernel
    def run(self):
        logger.info("Starting test")

        self.core.break_realtime()

        t_now_mu = now_mu()

        for i in range(9):
            at_mu(t_now_mu)
            self.urukul5_ch0.set(frequency=100e6, phase=0.0, amplitude=0.0)

        logger.info("Test done")
