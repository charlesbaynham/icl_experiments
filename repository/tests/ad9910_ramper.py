import logging
from typing import List

from artiq.coredevice.ad9910 import AD9910
from artiq.coredevice.core import Core
from artiq.coredevice.urukul import CPLD
from artiq.coredevice.zotino import Zotino
from artiq.experiment import delay
from artiq.experiment import EnumerationValue
from artiq.experiment import EnvExperiment
from artiq.experiment import kernel
from artiq.experiment import TFloat
from artiq.experiment import TInt32
from artiq.experiment import TList
from ndscan.experiment import ExpFragment
from ndscan.experiment import FloatParam
from ndscan.experiment import Fragment
from ndscan.experiment.entry_point import make_fragment_scan_exp
from ndscan.experiment.parameters import FloatParamHandle
from numpy import int32
from numpy import int64


logger = logging.getLogger(__name__)


class AD9910Ramper(EnvExperiment):
    def build(self):
        self.setattr_device("core")
        self.core: Core
        self.setattr_device("urukul5_ch0")
        self.urukul5_ch0: AD9910

    @kernel
    def run(self):
        self.core.reset()

        self.urukul5_ch0.init()

        delay(10e-3)

        dds = self.urukul5_ch0

        # Enable no-dwell
        # Set ramp rate:
        #   t_step = xxx
        #   f_step = minimum
        # Set ramp max and min

        dds.set_cfr2(drg_enable=1)

        # Pulse IO_UPDATE

    @kernel
    def extended_set_cfr2(
        self,
        dds: AD9910,
        asf_profile_enable: TInt32 = 1,
        drg_enable: TInt32 = 0,
        effective_ftw: TInt32 = 1,
        sync_validation_disable: TInt32 = 0,
        matched_latency_enable: TInt32 = 0,
        no_dwell_high: TInt32 = 0,
        no_dwell_low: TInt32 = 0,
    ):
        """Set CFR2. See the AD9910 datasheet for parameter meanings.

        This is a copy/paste of the ARTIQ implementation but with control of the NO-DWELL bits added

        This method does not pulse IO_UPDATE.

        :param asf_profile_enable: Enable amplitude scale from single tone profiles.
        :param drg_enable: Digital ramp enable.
        :param effective_ftw: Read effective FTW.
        :param sync_validation_disable: Disable the SYNC_SMP_ERR pin indicating
            (active high) detection of a synchronization pulse sampling error.
        :param matched_latency_enable: Simultaneous application of amplitude,
            phase, and frequency changes to the DDS arrive at the output

            * matched_latency_enable = 0: in the order listed
            * matched_latency_enable = 1: simultaneously.
        """
        from artiq.coredevice.ad9910 import _AD9910_REG_CFR2

        dds.write32(
            _AD9910_REG_CFR2,
            (asf_profile_enable << 24)
            | (drg_enable << 19)
            | (no_dwell_high << 18)
            | (no_dwell_low << 17)
            | (effective_ftw << 16)
            | (matched_latency_enable << 7)
            | (sync_validation_disable << 5),
        )

    @kernel
    def set_ramp_parameters_mu(
        self, dds: AD9910, freq_step_mu: TInt32, delay_mu: TInt32
    ):
        """Sets the upwards and downwards DRG ramp step sizes and delays

        This function does not enable the DRG.
        """
        from artiq.coredevice.ad9910 import (
            _AD9910_REG_RAMP_RATE,
            _AD9910_REG_RAMP_STEP,
        )

        # Write the same step size / ramp rates to both the up- and downwards ramps
        dds.write64(_AD9910_REG_RAMP_STEP, freq_step_mu, freq_step_mu)

        ramp_rate = delay_mu & 0xFFFF
        ramp_rate = ramp_rate | (ramp_rate << 16)
        dds.write32(_AD9910_REG_RAMP_RATE, ramp_rate)

    @kernel
    def set_ramp_parameters(self, dds: AD9910, freq_step: TFloat, delay: TFloat):
        """Sets the upwards and downwards DRG ramp step sizes and delays

        This function does not enable the DRG.
        """
        freq_step_mu = dds.frequency_to_ftw(freq_step)
        delay_mu = int32(round(dds.sysclk / 4 * delay))

        self.set_ramp_parameters_mu(dds, freq_step_mu, delay_mu)

    @kernel
    def set_ramp_limits_mu(
        self, dds: AD9910, frequency_low_mu: TInt32, frequency_high_mu: TInt32
    ):
        """Sets the high and low frequency limits for the DRG

        This function does not enable the DRG.
        """
        from artiq.coredevice.ad9910 import _AD9910_REG_RAMP_LIMIT

        dds.write64(_AD9910_REG_RAMP_LIMIT, frequency_high_mu, frequency_low_mu)

    @kernel
    def set_ramp_limits(
        self, dds: AD9910, frequency_low: TFloat, frequency_high: TFloat
    ):
        """Sets the high and low frequency limits for the DRG

        This function does not enable the DRG.
        """
        self.set_ramp_limits_mu(
            dds,
            dds.frequency_to_ftw(frequency_low),
            dds.frequency_to_ftw(frequency_high),
        )
