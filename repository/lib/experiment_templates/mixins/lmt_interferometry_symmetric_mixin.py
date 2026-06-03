import logging

from artiq.language import at_mu
from artiq.language import delay
from artiq.language import delay_mu
from artiq.language import kernel
from artiq.language import now_mu
from ndscan.experiment.parameters import FloatParam
from ndscan.experiment.parameters import FloatParamHandle
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

    def build_fragment(self):
        super().build_fragment()

        self.setattr_param_rebind(
            "first_lmt_freq_lower",
            self,
            original_name="first_lmt_freq",
            description="Detuning first LMT pulse on the lower arm",
            default=0.0e3,
        )
        self.first_lmt_freq_lower: FloatParamHandle

        self.setattr_param(
            "first_lmt_freq_upper",
            FloatParam,
            "Detuning first LMT pulse on the upper arm",
            default=0.0e3,
            unit="kHz",
        )
        self.first_lmt_freq_upper: FloatParamHandle

    @kernel
    def do_clock_interferometry(self):

        N = self.lmt_pulses_number.get()
        N_launch = 0
        t_pi_down = self.down_pulses_duration.get()
        t_first_pi = self.first_lmt_duration.get()

        # frequencies
        first_freq_lower = self.first_lmt_freq_lower.get()
        first_freq_upper = self.first_lmt_freq_upper.get()
        bs1_lmt_offset = self.bs1_lmt_offset_detuning.get()
        self.upper_mirror_offset_detuning.get()
        self.last_upper_mirror_lmt_freq.get()
        mirror_freq = self.mirror_pulse_freq.get()
        self.first_lower_mirror_lmt_freq.get()
        self.lower_mirror_offset_detuning.get()
        bs_detuning_lower = self.lower_arm_bs_detuning.get()
        self.last_selective_lower_bs_freq.get()
        self.last_bs_freq.get()

        # PI/2 PULSE
        self.first_beam_splitter(t_pi_down, N_launch)
        delay(100e-6)

        # Lower Rabi frequency on lower arm, up beam pulse
        if N > 1:
            self.clock_up_dds.set(
                frequency=self.clock_switch_frequency_handle.get()
                + self.up_switch_detuning_lower_intensity.get(),
                amplitude=self.clock_switch_amplitude_handle.get(),
                phase=self.calculate_phase_for_first_pi_by_2_pulse(),
            )

            delay_mu(8)
            self.do_selective_lmt_pulse(
                first_freq_lower, N_kicks=1 + N_launch, att=10.5, duration=t_first_pi
            )

        # Lower Rabi frequency on upper arm, up beam pulse
        if N > 2:
            self.do_selective_lmt_pulse(
                first_freq_upper, N_kicks=2 + N_launch, att=10.5, duration=t_first_pi
            )

        if N > 3:
            self.opening_lmt_series(
                N_lmt=N - 2,
                N_launch=N_launch,
                freq_offset_lower=bs_detuning_lower,
                freq_offset_upper=bs1_lmt_offset,
            )

        t_end_bs_mu = now_mu()
        # Do a Stark shifting pulse in the first dark time
        self.stark_shifter.do_stark_pulse()

        # dark time
        t_start_lmt_mirror_mu = t_end_bs_mu + self.core.seconds_to_mu(
            self.delay_between_interferometry_pulses.get()
        )

        at_mu(t_start_lmt_mirror_mu)

        delay(8e-9)

        self.mirror_pulse(t_pi_down, N_launch, mirror_freq)

        delay(50e-6)

    @kernel
    def opening_lmt_series(self, N_lmt, N_launch, freq_offset_lower, freq_offset_upper):
        if N_lmt % 2 != 0:
            raise ValueError("N_lmt must be even for symmetric interferometer")

        for i in range(int(N_lmt / 2)):

            # Lower arm
            self.lmt_series_start_up_launch_down(
                offset_det=freq_offset_lower,
                N_previous_pulses=i * 2 + N_launch + 1,
                N=2,
            )

            # upper arm
            self.lmt_series(
                offset_det=freq_offset_upper,
                N_previous_pulses=2 * i + 1 + N_launch + 3,
                N=2,
            )

        # extra couple of pulse on the lower arm to match for BS and selective pulse
        # on the upper arm
        self.lmt_series_start_up_launch_down(
            offset_det=0.0,
            N_previous_pulses=N_lmt + N_launch + 1,
            N=2,
        )

    @kernel
    def closing_lmt_series(self, N_lmt, N_launch, freq_offset_upper, freq_offset_lower):
        if N_lmt % 2 != 0:
            raise ValueError("N_lmt must be even for symmetric interferometer")

        for i in range(int(N_lmt / 2)):
            # lower arm
            self.lmt_series(
                offset_det=freq_offset_lower,
                N_previous_pulses=i * 2 + N_launch - N_lmt,
                N=2,
            )

            # upper arm
            self.lmt_series_start_up_launch_down(
                offset_det=freq_offset_upper,
                N_previous_pulses=i * 2 + N_lmt + N_launch,
                N=2,
            )

        # extra couple of pulse on the lower arm
        self.lmt_series(
            offset_det=0.0,
            N_previous_pulses=N_launch - 2,
            N=2,
        )
