import logging

from artiq.language import at_mu
from artiq.language import delay
from artiq.language import kernel
from artiq.language import now_mu
from pyaion.models import SUServoedBeam
from pyaion.models import UrukuledBeam

from repository.lib import constants
from repository.lib.experiment_templates.mixins.LMT_launch_mixins import (
    LMTInterferometryMixin,
)

CLOCK_UP_BEAM_INFO: UrukuledBeam = constants.URUKULED_BEAMS["clock_up"]
CLOCK_DOWN_BEAM_INFO: UrukuledBeam = constants.URUKULED_BEAMS["clock_down"]
CLOCK_BEAM_DELIVERY_INFO: SUServoedBeam = constants.SUSERVOED_BEAMS["clock_delivery"]

ramp_rate = constants.GRAVITY_DOPPLER_PER_SEC_CLOCK
momentum_kick = constants.MOMENTUM_KICK_DETUNING
start_opll_offset = 80e6

logger = logging.getLogger(__name__)


class LMTSymmetricInterferometryMixin(LMTInterferometryMixin):
    """
    Implements a symmetric LMT interferometer

    Kernel hooks used (multiple mixins cannot use the same hooks):
    * :meth:`~do_experiment_after_dipole_trap`
    * :meth:`~post_sequence_cleanup_hook_lmt`
    """

    @kernel
    def do_clock_interferometry(self):

        N = self.lmt_pulses_number.get()
        N_launch = 22
        t_pi_down = self.down_pulses_duration.get()

        # frequencies
        self.first_lmt_freq.get()
        bs1_lmt_offset = self.bs1_lmt_offset_detuning.get()
        self.upper_mirror_offset_detuning.get()
        self.last_upper_mirror_lmt_freq.get()
        self.mirror_pulse_freq.get()
        self.first_lower_mirror_lmt_freq.get()
        self.lower_mirror_offset_detuning.get()
        bs_detuning_lower = self.lower_arm_bs_detuning.get()
        self.last_selective_lower_bs_freq.get()
        self.last_bs_freq.get()

        # PI/2 PULSE
        self.first_beam_splitter(t_pi_down, N_launch)
        delay(100e-6)

        self.first_lmt_series(N, bs_detuning_lower, bs1_lmt_offset)

        t_end_bs_mu = now_mu()
        # Do a Stark shifting pulse in the first dark time
        self.stark_shifter.do_stark_pulse()

        # dark time
        t_start_lmt_mirror_mu = t_end_bs_mu + self.core.seconds_to_mu(
            self.delay_between_interferometry_pulses.get()
        )

        at_mu(t_start_lmt_mirror_mu)

    @kernel
    def first_lmt_series(self, N_lmt, freq_offset_lower, freq_offset_upper):
        for i in range(N_lmt / 2):

            # Lower arm
            self.lmt_series_start_up_launch_down(
                offset_det=freq_offset_lower, N_previous_pulses=i * 2, N=2
            )

            # upper arm
            self.lmt_series(
                offset_det=freq_offset_upper, N_previous_pulses=2 * i + 1, N=2
            )
