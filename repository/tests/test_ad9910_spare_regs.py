import logging

import numpy as np
from artiq.coredevice.ad9910 import _AD9910_REG_AUX_DAC
from artiq.coredevice.ad9910 import _AD9910_REG_CFR2
from artiq.coredevice.ad9910 import _AD9910_REG_PROFILE3
from artiq.coredevice.ad9910 import AD9910
from artiq.coredevice.core import Core
from artiq.coredevice.urukul import CFG_RST
from artiq.coredevice.urukul import CPLD
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

        self.channel: AD9910 = self.get_device(
            "urukul9910_aom_doublepass_689_red_injection"
        )
        self.urukul: CPLD = self.channel.cpld

        # self.setattr_argument(
        #     "value", NumberValue(default=0, step=1, ndecimals=0, type="int")
        # )
        # self.value: int

    @kernel
    def urukul_rst(self, dds: CPLD):
        """Pulse MASTER_RESET"""
        dds.cfg_write(self.cfg_reg | (1 << CFG_RST))
        delay(100e-3)
        dds.cfg_write(self.cfg_reg & ~(1 << CFG_RST))

    @kernel
    def run(self):
        self.core.break_realtime()

        self.urukul_rst(self.urukul)

        # profile_3 = self.channel.read64(_AD9910_REG_PROFILE3)

        # logger.info("Reading profile_3 = 0x%X", profile_3)

        # # aux_val |= 0xABCDEF00

        # mask = np.int64(0xFFFF) << 40

        # address_step_rate = (profile_3 & mask) >> 40

        # logger.info("address_step_rate = 0x%X", address_step_rate)
        # logger.info("mask = 0x%X", mask)

        # address_step_rate_new = np.int64(0xABCD)

        # profile_3_new = (profile_3 & (~mask)) | (address_step_rate_new << 40)

        # profile_3_MSB = np.int32((profile_3_new >> 32) & (0xFFFFFFFF))
        # profile_3_LSB = np.int32(profile_3_new & (0xFFFFFFFF))

        # logger.info("Writing profile_3 = 0x%X", profile_3_new)
        # logger.info("Writing msb = 0x%X", profile_3_MSB)
        # logger.info("Writing lsb = 0x%X", profile_3_LSB)

        # self.core.break_realtime()
        # self.channel.write64(_AD9910_REG_PROFILE3, profile_3_LSB, profile_3_MSB)

        # self.channel.cpld.io_update.pulse_mu(8)

        # delay(1e-3)

        # self.core.break_realtime()
        # renewed_profile_3 = self.channel.read64(_AD9910_REG_PROFILE3)

        # hi = (renewed_profile_3 >> 32) & 0xFFFFFFFF
        # lo = renewed_profile_3 & 0xFFFFFFFF

        # logger.info("Reading renewed_profile_3 = 0x%X, 0x%X", hi, lo)

        # self.core.break_realtime()
        # self.channel.write64(_AD9910_REG_PROFILE3, 0, 0)

        # self.channel.cpld.io_update.pulse_mu(8)

        # delay(1e-3)
