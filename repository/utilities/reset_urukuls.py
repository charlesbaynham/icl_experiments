import logging

from artiq.coredevice.core import Core
from artiq.coredevice.urukul import CFG_RST
from artiq.coredevice.urukul import CPLD as Urukul_CPLD
from artiq.coredevice.urukul import *
from artiq.experiment import EnvExperiment
from artiq.language import delay
from artiq.language import kernel
from pyaion.lib.utils import get_local_devices

logger = logging.getLogger(__name__)
REG_ADDR = 0x05


class ResetAllUrukuls(EnvExperiment):
    """
    Reset all Urukuls' AD991x devices

    Sometimes the AD9910s and AD9912s get stuck in a bad state, most often if
    you delete an experiment while its running. This experiment will attempt to
    save them by pulsing MASTER_RESET on *every* Urukul connected to the system.
    User beware.
    """

    def build(self):
        self.setattr_device("core")
        self.core: Core

        cpld_names = get_local_devices(self, Urukul_CPLD)

        self.cplds: list[Urukul_CPLD] = [self.get_device(name) for name in cpld_names]

    @kernel
    def run(self):
        self.core.reset()

        for cpld in self.cplds:
            self.urukul_rst(cpld)

        for cpld in self.cplds:
            self.read_status(cpld)

    @kernel
    def urukul_rst(self, cpld):
        # type:(CPLD) -> None

        """Pulse MASTER_RESET"""

        cpld.cfg_write(cpld.cfg_reg | (1 << CFG_RST))
        delay(10e-3)
        cpld.cfg_write(cpld.cfg_reg & ~(1 << CFG_RST))
        delay(1e-3)

    @kernel
    def read_status(self, cpld):
        # type:(CPLD) -> None

        self.core.break_realtime()
        status = cpld.sta_read()

        logger.info(
            "Status register for urukul cpld on channel %s: 0x%X",
            cpld.bus.channel,
            status,
        )
        logger.info("urukul_sta_rf_sw = %s", urukul_sta_rf_sw(status))
        logger.info("urukul_sta_smp_err = %s", urukul_sta_smp_err(status))
        logger.info("urukul_sta_pll_lock = %s", urukul_sta_pll_lock(status))
        logger.info("urukul_sta_ifc_mode = %s", urukul_sta_ifc_mode(status))
        logger.info("urukul_sta_proto_rev = %s", urukul_sta_proto_rev(status))
