import logging

from artiq.coredevice.ad9910 import _AD9910_REG_CFR2
from artiq.coredevice.ad9910 import AD9910
from artiq.coredevice.core import Core
from artiq.experiment import EnvExperiment
from artiq.experiment import delay
from artiq.experiment import kernel

logger = logging.getLogger(__name__)


class AD9910CFR2Writer(EnvExperiment):
    def build(self):
        self.setattr_device("core")
        self.core: Core

        self.setattr_device("urukul8_ch0")
        self.urukul8_ch0: AD9910

        self.dds = self.urukul8_ch0

    @kernel
    def run(self):
        self.core.reset()
        delay(100e-3)

        self.dds.init()

        self.core.break_realtime()
        delay(100e-3)

        # Read the CFR2 register
        cfr2 = self.read_reg()

        # Write into the "open" bits
        OPEN_BITS_OFFSET = 25

        data = 0b10101010

        cfr2_modified = cfr2 & ~(0xFF << OPEN_BITS_OFFSET)
        cfr2_modified |= data << OPEN_BITS_OFFSET

        logger.info("Writing 0x%08x to CFR2", cfr2_modified)

        self.core.break_realtime()
        self.dds.write32(_AD9910_REG_CFR2, cfr2_modified)

        self.read_reg()

    @kernel
    def read_reg(self):
        cfr2 = self.dds.read32(_AD9910_REG_CFR2)

        logger.info("CFR2 = 0x%08x", cfr2)

        return cfr2
