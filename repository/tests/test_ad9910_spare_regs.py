"""
The AD9910 has two spare registers, numbers 5 and 6. I'd like to write a magic
number to these so that I can read it back and detect whether the AD9910 (and,
by extension, the rest of the urukul) has been initiated so that I can skip
reinitialisation.
"""
import logging

import numpy as np
from artiq.coredevice.ad9910 import _AD9910_REG_AUX_DAC
from artiq.coredevice.ad9910 import _AD9910_REG_CFR2
from artiq.coredevice.ad9910 import _AD9910_REG_PROFILE3
from artiq.coredevice.ad9910 import AD9910
from artiq.coredevice.core import Core
from artiq.experiment import delay
from artiq.experiment import EnvExperiment
from artiq.experiment import kernel
from artiq.experiment import NumberValue
from artiq.experiment import TInt64

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

        profile_3 = self.urukul.read64(_AD9910_REG_PROFILE3)

        logger.info("Reading profile_3 = 0x%X", profile_3)

        # aux_val |= 0xABCDEF00

        mask = np.int64(0xFFFF) << 40

        address_step_rate = (profile_3 & mask) >> 40

        logger.info("address_step_rate = 0x%X", address_step_rate)
        logger.info("mask = 0x%X", mask)

        address_step_rate_new = np.int64(0xABCD)

        profile_3_new = (profile_3 & (~mask)) | (address_step_rate_new << 40)

        profile_3_MSB = np.int32((profile_3_new >> 32) & (0xFFFFFFFF))
        profile_3_LSB = np.int32(profile_3_new & (0xFFFFFFFF))

        logger.info("Writing profile_3 = 0x%X", profile_3_new)
        logger.info("Writing msb = 0x%X", profile_3_MSB)
        logger.info("Writing lsb = 0x%X", profile_3_LSB)

        self.core.break_realtime()
        self.urukul.write64(_AD9910_REG_PROFILE3, profile_3_LSB, profile_3_MSB)

        self.urukul.cpld.io_update.pulse_mu(8)

        delay(1e-3)

        self.core.break_realtime()
        renewed_profile_3 = self.urukul.read64(_AD9910_REG_PROFILE3)

        logger.info("Reading renewed_profile_3 = 0x%X", renewed_profile_3)

        self.core.break_realtime()
        self.urukul.write64(_AD9910_REG_PROFILE3, 0, 0)

        self.urukul.cpld.io_update.pulse_mu(8)

        delay(1e-3)
