"""
The AD9910 has two spare registers, numbers 5 and 6. I'd like to write a magic
number to these so that I can read it back and detect whether the AD9910 (and,
by extension, the rest of the urukul) has been initiated so that I can skip
reinitialisation.
"""

from artiq.experiment import EnvExperiment, NumberValue, kernel
from artiq.coredevice.ad9910 import AD9910

import logging

logger = logging.getLogger(__name__)
REG_ADDR = 0x05


class WriteToAD9910SpareRegistry(EnvExperiment):
    def build(self):
        self.setattr_device("core")

        self.urukul: AD9910 = self.get_device(
            "urukul9910_aom_doublepass_689_red_injection"
        )

        self.setattr_argument(
            "value", NumberValue(default=0, step=1, ndecimals=0, type="int")
        )
        self.value: int

    @kernel
    def run(self):
        self.core.break_realtime()

        previous_value = self.urukul.read32(REG_ADDR)

        logger.info("Previous value: 0x%X", previous_value)

        logger.info("Writing new value: 0x%X", self.value)

        self.urukul.write32(REG_ADDR, self.value & 0xFFFF)

        new_value = self.urukul.read32(REG_ADDR)

        logger.info("Re-reading value: 0x%X", new_value)
