import logging
from typing import *

from artiq.experiment import *
from numpy import int64
from pyaion.lib.utils import get_local_devices

logger = logging.getLogger(__name__)


class WriteAD9910FTW(EnvExperiment):
    def build(self):
        self.setattr_device("core")
        self.core: Core

        ad9910_devices = get_local_devices(self, AD9910)

        self.setattr_argument("dds_name", EnumerationValue(ad9910_devices))

        self.dds: AD9910 = self.get_device(self.dds_name)

        self.setattr_argument("freq", NumberValue(default=10e6, unit="MHz"))

    @kernel
    def run(self):
        t_one_cycle_mu = int64(self.core.ref_multiplier)

        self.core.reset()

        logger.warning(
            "Setting frequency to %.1f MHz",
            self.freq * 1e6,
        )

        self.core.break_realtime()
        delay(10e-3)

        self.dds.set_frequency(self.freq)

        # We do this in a separate loop so that the IO_updates are
        # almost simultaneous. If we were willing to consume all the
        # RTIO lanes, they could be truely simultaneous
        delay_mu(int64(self.dds.sync_data.io_update_delay))
        self.dds.cpld.io_update.pulse_mu(8)  # assumes 8 mu > t_SYN_CCLK
