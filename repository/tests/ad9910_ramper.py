import logging

from artiq.coredevice.ad9910 import _AD9910_REG_CFR2
from artiq.coredevice.ad9910 import _AD9910_REG_RAMP_LIMIT
from artiq.coredevice.ad9910 import _AD9910_REG_RAMP_RATE
from artiq.coredevice.ad9910 import _AD9910_REG_RAMP_STEP
from artiq.coredevice.ad9910 import AD9910
from artiq.coredevice.core import Core
from artiq.experiment import delay
from artiq.experiment import EnvExperiment
from artiq.experiment import kernel
from artiq.experiment import NumberValue
from artiq.experiment import TFloat
from artiq.experiment import TInt32
from numpy import ceil
from numpy import int32


logger = logging.getLogger(__name__)


class AD9910Ramper(EnvExperiment):
    def build(self):
        self.setattr_device("core")
        self.core: Core
        self.setattr_device("urukul8_ch0")
        self.urukul8_ch0: AD9910

        self.dds = self.urukul8_ch0

        self.setattr_argument(
            "f_min", NumberValue(default=10e6, unit="MHz", ndecimals=6)
        )
        self.setattr_argument(
            "f_max", NumberValue(default=20e6, unit="MHz", ndecimals=6)
        )
        self.setattr_argument(
            "df_dt", NumberValue(default=1e6, unit="MHz", ndecimals=6)
        )

    @kernel
    def run(self):
        self.core.reset()
        self.dds.init()

        delay(10e-3)

        self.core.break_realtime()
        self.start_ramp(self.df_dt, self.f_min, self.f_max)

    @kernel
    def extended_set_cfr2(
        self,
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
        :param no_dwell_high: Set the NO-DWELL high bit.
        :param no_dwell_low: Set the NO-DWELL low bit.
        :param effective_ftw: Read effective FTW.
        :param sync_validation_disable: Disable the SYNC_SMP_ERR pin indicating
            (active high) detection of a synchronization pulse sampling error.
        :param matched_latency_enable: Simultaneous application of amplitude,
            phase, and frequency changes to the DDS arrive at the output

            * matched_latency_enable = 0: in the order listed
            * matched_latency_enable = 1: simultaneously.
        """
        self.dds.write32(
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
    def set_ramp_parameters_mu(self, freq_step_mu: TInt32, delay_mu: TInt32):
        """Sets the upwards and downwards DRG ramp step sizes and delays

        This function does not enable the DRG.
        """

        # Write the same step size / ramp rates to both the up- and downwards ramps
        self.dds.write64(_AD9910_REG_RAMP_STEP, freq_step_mu, freq_step_mu)

        ramp_rate = delay_mu & 0xFFFF
        ramp_rate = ramp_rate | (ramp_rate << 16)
        self.dds.write32(_AD9910_REG_RAMP_RATE, ramp_rate)

    @kernel
    def set_ramp_parameters(self, freq_step: TFloat, delay: TFloat):
        """Sets the upwards and downwards DRG ramp step sizes and delays

        This function does not enable the DRG.
        """
        freq_step_mu = self.dds.frequency_to_ftw(freq_step)
        delay_mu = int32(round(self.dds.sysclk / 4 * delay))

        self.set_ramp_parameters_mu(freq_step_mu, delay_mu)

    @kernel
    def set_ramp_limits_mu(self, frequency_low_mu: TInt32, frequency_high_mu: TInt32):
        """Sets the high and low frequency limits for the DRG

        This function does not enable the DRG.
        """
        self.dds.write64(_AD9910_REG_RAMP_LIMIT, frequency_high_mu, frequency_low_mu)

    @kernel
    def set_ramp_limits(self, frequency_low: TFloat, frequency_high: TFloat):
        """Sets the high and low frequency limits for the DRG

        This function does not enable the DRG.
        """
        self.set_ramp_limits_mu(
            self.dds.frequency_to_ftw(frequency_low),
            self.dds.frequency_to_ftw(frequency_high),
        )

    @kernel
    def start_ramp(self, rate: TFloat, freq_low: TFloat, freq_high: TFloat):
        """Configures a triangle-wave ramp with the given rate in Hz/s and
        frequency limits.

        This method sets the step size to the smallest possible amount that will
        permit the desired ramp rate then varies the time between steps to get
        the requested rate.

        This function enables the DRG immediately.
        """

        factor = (4.0 * (2.0**32.0)) * rate / self.dds.sysclk**2.0

        freq_step_mu = int32(ceil(factor))
        delay_mu = int32(round(freq_step_mu / factor))

        achieved_ramp_rate = (
            freq_step_mu * self.dds.sysclk**2 / 4.0 / 2.0**32.0 / delay_mu
        )
        logger.info("freq_step_mu = %s", freq_step_mu)
        logger.info("delay_mu = %s", delay_mu)
        logger.info("achieved_ramp_rate = %s", achieved_ramp_rate)
        self.core.break_realtime()

        self.set_ramp_limits(freq_low, freq_high)
        self.set_ramp_parameters_mu(freq_step_mu, delay_mu)
        self.extended_set_cfr2(drg_enable=1, no_dwell_low=1, no_dwell_high=1)

        # Pulse IO_UPDATE
        self.dds.cpld.io_update.pulse_mu(8)
