"""
The AD9910 has two spare registers, numbers 5 and 6. I'd like to write a magic
number to these so that I can read it back and detect whether the AD9910 (and,
by extension, the rest of the urukul) has been initiated so that I can skip
reinitialisation.
"""
import logging

from artiq.coredevice.ad9910 import _AD9910_REG_AUX_DAC
from artiq.coredevice.ad9910 import _AD9910_REG_CFR2
from artiq.coredevice.ad9910 import _AD9910_REG_PROFILE7
from artiq.coredevice.ad9910 import AD9910
from artiq.coredevice.core import Core
from artiq.experiment import EnvExperiment
from artiq.experiment import kernel
from artiq.experiment import NumberValue

logger = logging.getLogger(__name__)
REG_ADDR = 0x05


class WriteToAD9910SpareRegistry(EnvExperiment):
    def build(self):
        self.setattr_device("core")
        self.core: Core

        self.urukul: AD9910 = self.get_device(
            "urukul9910_aom_doublepass_689_red_injection"
        )

        # self.setattr_argument(
        #     "value", NumberValue(default=0, step=1, ndecimals=0, type="int")
        # )
        # self.value: int

    @kernel
    def run(self):
        self.core.break_realtime()

        profile_7 = self.urukul.read64(_AD9910_REG_PROFILE7)

        logger.info("Reading val = 0x%X", profile_7)

        # aux_val |= 0xABCDEF00

        mask = 0xFFFF << 40

        address_step_rate = (profile_7 & mask) >> 40

        logger.info("address_step_rate = 0x%X", address_step_rate)

        address_step_rate_new = 0xABCD

        profile_7_new = (profile_7 & (~mask)) | (address_step_rate_new << 40)

        logger.info("Writing asr = 0x%X", profile_7_new)

        # self.core.break_realtime()
        # self.urukul.write64(_AD9910_REG_PROFILE7, profile_7_new)

        # self.core.break_realtime()
        # aux_val = self.urukul.read32(_AD9910_REG_PROFILE7)

        # logger.info("Reading val = 0x%X", aux_val)
