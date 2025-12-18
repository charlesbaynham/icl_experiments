import logging

from artiq.language import at_mu
from artiq.language import delay
from artiq.language import delay_mu
from artiq.language import kernel
from artiq.language import now_mu
from ndscan.experiment.parameters import FloatParam
from ndscan.experiment.parameters import FloatParamHandle
from ndscan.experiment.parameters import IntParam
from ndscan.experiment.parameters import IntParamHandle
from numpy import int64
from pyaion.models import SUServoedBeam
from pyaion.models import UrukuledBeam

from repository.lib import constants
from repository.lib.experiment_templates.dipole_trap_experiment import (
    DipoleTrapWithExperiment,
)
from repository.lib.experiment_templates.mixins.clock_interferometry import (
    ClockInterferometryBase,
)
from repository.lib.experiment_templates.mixins.clock_spectroscopy import (
    ClockSpectroscopyBase,
)
from repository.lib.experiment_templates.red_mot_experiment import RedMOTWithExperiment
from repository.lib.fragments.clock_opll_controller import ClockOPLLController
from repository.lib.fragments.pulse_shaping import JessePulse

CLOCK_UP_BEAM_INFO: UrukuledBeam = constants.URUKULED_BEAMS["clock_up"]
CLOCK_DOWN_BEAM_INFO: UrukuledBeam = constants.URUKULED_BEAMS["clock_down"]
CLOCK_BEAM_DELIVERY_INFO: SUServoedBeam = constants.SUSERVOED_BEAMS["clock_delivery"]

ramp_rate = constants.GRAVITY_DOPPLER_PER_SEC_CLOCK
start_opll_offset = 80e6

logger = logging.getLogger(__name__)


class LMTBase(
    ClockSpectroscopyBase,
    RedMOTWithExperiment,
):
    """
    Base for succession of clock pulses with up and down beams

    """

    def build_fragment(self):
        super().build_fragment()

        self.setattr_param(
            "down_switch_detuning",
            FloatParam,
            "Detuning on the down switch AOM",
            default=constants.LMT_DOWN_BEAM_SHIFT,
            unit="kHz",
        )
        self.down_switch_detuning: FloatParamHandle

        self.setattr_param(
            "up_switch_detuning_higher_intensity",
            FloatParam,
            "Detuning on the up switch AOM during lmt pulses",
            default=2.8e3,
            unit="kHz",
        )
        self.up_switch_detuning_higher_intensity: FloatParamHandle

        self.setattr_param(
            "clearout_duration",
            FloatParam,
            "Duration of 461 clearout pulse after LMT pulse",
            default=constants.LMT_PULSE_CLEAROUT_DURATION,
            unit="us",
        )
        self.shelving_pulse_clearout_duration: FloatParamHandle

        if not hasattr(self, "spectroscopy_pulse_time"):
            self.setattr_param(
                "spectroscopy_pulse_time",
                FloatParam,
                "Duration of an up beam pulse",
                default=constants.CLOCK_PI_TIME,
                unit="us",
            )
            self.spectroscopy_pulse_time: FloatParamHandle

        self.setattr_param(
            "down_pulses_duration",
            FloatParam,
            "Duration of a down beam pulse",
            default=constants.DOWN_CLOCK_BEAM_PI_TIME,
            unit="us",
        )
        self.down_pulses_duration: FloatParamHandle

        self.setattr_param(
            "momentum_kick",
            FloatParam,
            "Momentum kick",
            default=constants.MOMENTUM_KICK_DETUNING,
            unit="kHz",
        )
        self.momentum_kick: FloatParamHandle

        if not hasattr(self, "clock_opll"):
            self.setattr_fragment("clock_opll", ClockOPLLController)
            self.clock_opll: ClockOPLLController

    # use if we start in the excited state
    @kernel
    def lmt_series(self, offset_det, N_previous_pulses, N):

        kick = self.momentum_kick.get()
        t_drop = self.get_t_start_shelving()

        for i in range(N):

            if i % 2 == 0:
                down_offset = offset_det
                pulse_type = "down"
            else:
                down_offset = 0.0
                pulse_type = "up"

            t_start_lmt_pulse_mu = now_mu() + self.core.seconds_to_mu(1e-6)
            total_ramp_time = self.core.mu_to_seconds(t_start_lmt_pulse_mu - t_drop)

            f_i = (
                start_opll_offset
                + (-1) ** (i + 1) * total_ramp_time * ramp_rate
                + (i + N_previous_pulses) * (-1) ** (i) * kick
                + (-1) ** i * down_offset
            )

            # fire the pulse
            self.fire_lmt_pulse(f_i, pulse_type, t_start_lmt_pulse_mu)

    @kernel
    def launch_series(self, offset_det, N_previous_pulses, N):

        kick = self.momentum_kick.get()
        t_drop = self.get_t_start_shelving()

        for i in range(N):

            if i % 2 == 0:
                pulse_type = "down"
            else:
                pulse_type = "up"

            t_start_lmt_pulse_mu = now_mu() + self.core.seconds_to_mu(1e-6)
            total_ramp_time = self.core.mu_to_seconds(t_start_lmt_pulse_mu - t_drop)

            f_i = (
                start_opll_offset
                + (-1) ** (i + 1) * total_ramp_time * ramp_rate
                + (i + N_previous_pulses) * (-1) ** (i) * kick
                + (-1) ** i * offset_det
            )

            # fire the pulse
            self.fire_lmt_pulse(f_i, pulse_type, t_start_lmt_pulse_mu)

            # Clear out the ground state
            # if pulse_type == "up":
            #     self.fluorescence_pulse.do_imaging_pulse(
            #         duration=self.clearout_duration.get(),
            #         ignore_final_shutters=True,
            #     )
            #     delay(8e-9)

    # use if we start in the ground state
    @kernel
    def lmt_series_start_up(self, offset_det, N_previous_pulses, N):
        kick = self.momentum_kick.get()
        t_drop = self.get_t_start_shelving()

        t_start_ramp = now_mu()
        for i in range(N):

            # start with up pulse
            if i % 2 == 0:
                down_offset = 0.0
                pulse_type = "up"
            else:
                down_offset = offset_det
                pulse_type = "down"

            f_i = (
                start_opll_offset
                + (-1) ** (i) * total_ramp_time * ramp_rate
                + (i + N_previous_pulses) * (-1) ** (i + 1) * kick
                + (-1) ** (i + 1) * down_offset
            )

            t_start_lmt_pulse_mu = now_mu() + self.core.seconds_to_mu(1e-6)
            total_ramp_time = self.core.mu_to_seconds(t_start_lmt_pulse_mu - t_drop)

            # fire the pulse
            self.fire_lmt_pulse(f_i, pulse_type, t_start_lmt_pulse_mu)

            # Clear out the ground state
            # if pulse_type == "down":
            #     self.fluorescence_pulse.do_imaging_pulse(
            #         duration=self.clearout_duration.get(),
            #         ignore_final_shutters=True,
            #     )
            #     delay(8e-9)

    @kernel
    def lmt_series_start_down_launch_down(self, offset_det, N_previous_pulses, N):
        kick = self.momentum_kick.get()
        t_drop = self.get_t_start_shelving()

        for i in range(N):

            # start with down pulse
            if i % 2 == 0:
                down_offset = offset_det
                pulse_type = "down"

            else:
                down_offset = 0.0
                pulse_type = "up"

            t_start_lmt_2_pulse_mu = now_mu() + self.core.seconds_to_mu(1e-6)
            total_ramp_time = self.core.mu_to_seconds(t_start_lmt_2_pulse_mu - t_drop)

            f_i = (
                start_opll_offset
                + (-1) ** (i + 1) * total_ramp_time * ramp_rate
                + i * (-1) ** (i + 1) * kick
                + N_previous_pulses * (-1) ** (i) * kick
                + (-1) ** (i) * (down_offset)
            )

            # fire the pulse
            self.fire_lmt_pulse(f_i, pulse_type, t_start=t_start_lmt_2_pulse_mu)

    @kernel
    def fire_lmt_pulse(self, start_freq, type, t_start):
        # stop the ramp
        self.clock_opll.clock_frequency_ramper.stop_ramp()
        # set the offset frequency
        self.clock_opll.clock_OPLL_offset.set(start_freq)

        if type == "down":
            # ramp the offset downwards
            self.clock_opll.clock_frequency_ramper.start_ramp(
                ramp_rate,
                start_freq - 1e6,
                start_freq,
                wave_type=2,
            )
            delay_mu(8)
            # pulse the down beam
            at_mu(t_start)
            self.clock_down_dds.sw.on()
            delay(self.down_pulses_duration.get())
            self.clock_down_dds.sw.off()

        if type == "up":
            # ramp the offset upwards
            self.clock_opll.clock_frequency_ramper.start_ramp(
                ramp_rate,
                start_freq,
                start_freq + 2e6,
                wave_type=1,
            )
            delay_mu(8)

            # pulse the up beam
            at_mu(t_start)
            self.clock_up_dds.sw.on()
            delay(self.spectroscopy_pulse_time.get())
            self.clock_up_dds.sw.off()
        delay(25e-6)

    @kernel
    def calculate_frequency_for_first_lmt_pulse(
        self, t_pulse_start_mu: int64, t_pi_pulse: float
    ) -> float:
        return 0.0

    @kernel
    def calculate_frequency_for_second_lmt_pulse(
        self,
        t_pulse_start_mu: int64,
    ) -> float:
        return 0.0

    @kernel
    def calculate_frequency_for_selective_lmt_pulse(
        self, t_pulse_start_mu: int64, N_kicks: int64
    ) -> float:
        return 0.0

    @kernel
    def get_t_start_shelving(self) -> int64:
        return 0.0


class LMTLaunchMixin(LMTBase, DipoleTrapWithExperiment):
    """
    Implements LMT launch after the dipole trap

    Kernel hooks used (multiple mixins cannot use the same hooks):

    * :meth:`~launch_hook`
    """

    def build_fragment(self):
        super().build_fragment()

        self.setattr_param(
            "lmt_launch_pulses_number",
            IntParam,
            "Number of pulses for LMT launch",
            default=10,
        )
        self.lmt_launch_pulses_number: IntParamHandle

        self.setattr_param(
            "lmt_launch_offset_detuning",
            FloatParam,
            "Detuning for launch LMT series",
            default=constants.LMT_OFFSET_DETUNING,
            unit="kHz",
        )
        self.lmt_launch_offset_detuning: FloatParamHandle

    @kernel
    def launch_hook(self):
        # prepare delivery and switch aoms
        self.prepare_clock_delivery_aom()

        self.clock_down_dds.set(
            frequency=self.clock_switch_frequency_handle.get()
            + self.down_switch_detuning.get(),
            amplitude=self.clock_switch_amplitude_handle.get(),
        )

        self.clock_up_dds.set(
            frequency=self.clock_switch_frequency_handle.get()
            + self.up_switch_detuning_higher_intensity.get(),
            amplitude=self.clock_switch_amplitude_handle.get(),
        )
        delay_mu(16)
        start_detuning = self.lmt_launch_offset_detuning.get()
        lmt_number = self.lmt_launch_pulses_number.get()
        self.launch_series(start_detuning, N_previous_pulses=1, N=lmt_number)
        # Clear out the ground state
        self.fluorescence_pulse.do_imaging_pulse(
            duration=self.clearout_duration.get(),
            ignore_final_shutters=True,
        )
        delay_mu(8)


class LMTInterferometryMixin(
    LMTBase, ClockInterferometryBase, DipoleTrapWithExperiment
):
    """
    Implements LMT interferometry after the launch

    Kernel hooks used (multiple mixins cannot use the same hooks):

    * :meth:`~do_experiment_after_dipole_trap`
    """

    def build_fragment(self):
        super().build_fragment()

        self.setattr_param(
            "lmt_pulses_number",
            IntParam,
            "Number of pulses for LMT interferometry",
            default=7,
        )
        self.lmt_pulses_number: IntParamHandle

        self.setattr_param(
            "up_switch_detuning_lower_intensity",
            FloatParam,
            "Detuning on the up switch AOM during selective pulse",
            default=0.5e3,
            unit="kHz",
        )
        self.up_switch_detuning_lower_intensity: FloatParamHandle

        self.setattr_param(
            "first_lmt_freq",
            FloatParam,
            "Detuning 1st LMT pulse",
            default=0.2e3,
            unit="kHz",
        )
        self.first_lmt_freq: FloatParamHandle

        self.setattr_param(
            "bs1_lmt_offset_detuning",
            FloatParam,
            "LMT detuning after 1st BS",
            default=0e3,
            unit="kHz",
        )
        self.bs1_lmt_offset_detuning: FloatParamHandle

        self.setattr_param(
            "upper_mirror_offset_detuning",
            FloatParam,
            "LMT detuning for upper arm mirror",
            default=0.0,
            unit="kHz",
        )
        self.upper_mirror_offset_detuning: FloatParamHandle

        self.setattr_param(
            "last_upper_mirror_lmt_freq",
            FloatParam,
            "Detuning last upper arm mirror LMT pulse",
            default=0.0,
            unit="kHz",
        )
        self.last_upper_mirror_lmt_freq: FloatParamHandle

        self.setattr_param(
            "mirror_pulse_freq",
            FloatParam,
            "Frequency detuning for the mirror pulse",
            default=0.0,
            unit="kHz",
        )
        self.mirror_pulse_freq: FloatParamHandle

        self.setattr_param(
            "first_lower_mirror_lmt_freq",
            FloatParam,
            "Detuning first lower arm mirror LMT pulse",
            default=0.0,
            unit="kHz",
        )
        self.first_lower_mirror_lmt_freq: FloatParamHandle

        self.setattr_param(
            "lower_mirror_offset_detuning",
            FloatParam,
            "LMT detuning for lower arm mirror",
            default=0.0,
            unit="kHz",
        )
        self.lower_mirror_offset_detuning: FloatParamHandle

        self.setattr_param(
            "lower_arm_bs_detuning",
            FloatParam,
            "Detuning BS LMT series on lower arm",
            default=0.0,
            unit="kHz",
        )
        self.lower_arm_bs_detuning: FloatParamHandle

        self.setattr_param(
            "last_selective_lower_bs_freq",
            FloatParam,
            "Frequency detuning for last selective lower BS",
            default=0.0,
            unit="kHz",
        )
        self.last_selective_lower_bs_freq: FloatParamHandle

        self.setattr_param(
            "last_bs_freq",
            FloatParam,
            "Frequency detuning for last BS",
            default=0.0,
            unit="kHz",
        )
        self.last_bs_freq: FloatParamHandle

        self.setattr_param(
            "first_lmt_duration",
            FloatParam,
            "Duration of the selective LMT pulse",
            default=95e-6,
            unit="us",
        )
        self.first_lmt_duration: FloatParamHandle

    @kernel
    def do_experiment_after_dipole_trap_hook(self):
        self.do_clock_interferometry()

    @kernel
    def do_clock_interferometry(self):
        self.prepare_clock_delivery_aom()
        delay_mu(16)

        N = self.lmt_pulses_number.get()
        t_pi_down = self.down_pulses_duration.get()
        t_first_pi = self.first_lmt_duration.get()

        # frequencies
        first_freq = self.first_lmt_freq.get()
        bs1_lmt_offset = self.bs1_lmt_offset_detuning.get()
        upper_mirror_offset = self.upper_mirror_offset_detuning.get()
        last_upper_mirror_freq = self.last_upper_mirror_lmt_freq.get()
        mirror_freq = self.mirror_pulse_freq.get()
        first_lower_mirror_freq = self.first_lower_mirror_lmt_freq.get()
        lower_mirror_offset = self.lower_mirror_offset_detuning.get()
        bs_detuning_lower = self.lower_arm_bs_detuning.get()
        last_selective_lower_bs_freq = self.last_selective_lower_bs_freq.get()
        last_bs_freq = self.last_bs_freq.get()

        t_start_first_pulse_mu = now_mu() + self.core.seconds_to_mu(
            2e-6
        )  # Add a tiny delay to give us enough time to write to the DDS

        self.clock_opll.clock_frequency_ramper.stop_ramp()
        delay_mu(8)

        self.clock_opll.clock_OPLL_offset.set(
            start_opll_offset
            + bs1_lmt_offset
            + self.calculate_frequency_for_first_pi_by_2_pulse(
                t_pulse_start_mu=t_start_first_pulse_mu,
                t_pi_pulse=t_pi_down,
            )
            + 4 * 9.4e3
        )

        self.clock_down_dds.set(
            frequency=self.clock_switch_frequency_handle.get()
            + self.down_switch_detuning.get(),
            amplitude=self.clock_switch_amplitude_handle.get(),
            phase=self.calculate_phase_for_first_pi_by_2_pulse(),
        )

        # PI/2 PULSE DOWN BEAM
        at_mu(t_start_first_pulse_mu)
        self.clock_down_dds.sw.off()
        delay(t_pi_down / 2)
        self.clock_down_dds.sw.off()

        self.clock_up_dds.set(
            frequency=self.clock_switch_frequency_handle.get()
            + self.up_switch_detuning_lower_intensity.get(),
            amplitude=self.clock_switch_amplitude_handle.get(),
            phase=self.calculate_phase_for_first_pi_by_2_pulse(),
        )

        delay(1e-6)

        # First pulse with a lower Rabi frequency, up beam pulse
        if N > 1:
            self.do_selective_lmt_pulse(first_freq, N_kicks=6, duration=t_first_pi)

            # Clear out the ground state
            self.fluorescence_pulse.do_imaging_pulse(
                duration=self.clearout_duration.get(),
                ignore_final_shutters=True,
            )
            delay(8e-9)

        self.clock_up_dds.set(
            frequency=self.clock_switch_frequency_handle.get()
            + self.up_switch_detuning_higher_intensity.get(),
            amplitude=self.clock_switch_amplitude_handle.get(),
            phase=self.calculate_phase_for_first_pi_by_2_pulse(),
        )

        # LMT sequence on upper arm, starting on the excited state at n=2
        if N > 2:
            self.lmt_series(bs1_lmt_offset, N_previous_pulses=7, N=N - 2)

        delay_mu(8)
        t_end_bs_mu = now_mu()

        # Do a Stark shifting pulse in the first dark time
        self.stark_shifter.do_stark_pulse()

        # dark time
        t_start_lmt_mirror_mu = t_end_bs_mu + self.core.seconds_to_mu(
            self.delay_between_interferometry_pulses.get()
        )

        # LMT sequence on upper arm, momentum downwards
        at_mu(t_start_lmt_mirror_mu)
        self.lmt_series_start_down_launch_down(
            upper_mirror_offset, N_previous_pulses=N + 4, N=N - 2
        )
        delay_mu(8)

        # stark shift for low intensity up beam
        self.clock_up_dds.set(
            frequency=self.clock_switch_frequency_handle.get()
            + self.up_switch_detuning_lower_intensity.get(),
            amplitude=self.clock_switch_amplitude_handle.get(),
            phase=self.calculate_phase_for_first_pi_by_2_pulse(),
        )

        # Clear out the ground state
        self.fluorescence_pulse.do_imaging_pulse(
            duration=self.clearout_duration.get(),
            ignore_final_shutters=True,
        )
        delay(8e-9)

        # last pulse with a lower Rabi frequency, up beam pulse
        self.do_selective_lmt_pulse(
            last_upper_mirror_freq, N_kicks=6, duration=t_first_pi
        )

        delay(8e-9)
        # Phase step
        self.clock_down_dds.set(
            frequency=self.clock_switch_frequency_handle.get()
            + self.down_switch_detuning.get(),
            amplitude=self.clock_switch_amplitude_handle.get(),
            phase=self.calculate_phase_for_pi_pulse(),
        )

        # delay to write onto the dds
        delay(1e-6)

        # MIRROR PULSE DOWN BEAM
        t_start_mirror_pulse_mu = now_mu() + self.core.seconds_to_mu(
            1e-6
        )  # Add a tiny delay to give us enough time to write to the DDS

        self.clock_opll.clock_OPLL_offset.set(
            start_opll_offset
            + self.calculate_frequency_for_pi_pulse(
                t_pulse_start_mu=t_start_mirror_pulse_mu,
                t_pi_pulse=t_pi_down,
            )
            + mirror_freq
            + 3 * 9.4e3
        )
        at_mu(t_start_mirror_pulse_mu)
        self.clock_down_dds.sw.on()
        delay(t_pi_down)
        self.clock_down_dds.sw.off()

        delay(1e-6)

        # first lower arm mirror pulse with a lower Rabi frequency, up beam pulse
        self.do_selective_lmt_pulse(
            first_lower_mirror_freq, N_kicks=6, duration=t_first_pi
        )

        # stark shift for high intensity up beam
        self.clock_up_dds.set(
            frequency=self.clock_switch_frequency_handle.get()
            + self.up_switch_detuning_higher_intensity.get(),
            amplitude=self.clock_switch_amplitude_handle.get(),
            phase=self.calculate_phase_for_first_pi_by_2_pulse(),
        )

        # Clear out the ground state
        self.fluorescence_pulse.do_imaging_pulse(
            duration=self.clearout_duration.get(),
            ignore_final_shutters=True,
        )
        delay(8e-9)

        # LMT series on lower arm, start from second pulse, down beam
        self.lmt_series(lower_mirror_offset, N_previous_pulses=7, N=N - 2)
        delay_mu(8)

        # Phase step
        delay(self.delay_between_interferometry_pulses.get())

        # LMT sequence on lower arm, momentum downwards
        self.lmt_series_start_down_launch_down(
            bs_detuning_lower, N_previous_pulses=N + 4, N=N - 2
        )

        # stark shift for low intensity up neam
        self.clock_up_dds.set(
            frequency=self.clock_switch_frequency_handle.get()
            + self.up_switch_detuning_lower_intensity.get(),
            amplitude=self.clock_switch_amplitude_handle.get(),
            phase=self.calculate_phase_for_first_pi_by_2_pulse(),
        )

        # Clear out the ground state
        self.fluorescence_pulse.do_imaging_pulse(
            duration=self.clearout_duration.get(),
            ignore_final_shutters=True,
        )
        delay(8e-9)

        # last lower arm bs pulse with a lower Rabi frequency, up beam pulse
        self.do_selective_lmt_pulse(
            last_selective_lower_bs_freq, N_kicks=6, duration=t_first_pi
        )

        delay(8e-9)

        t_start_last_pulse_mu = now_mu() + self.core.seconds_to_mu(
            2e-6
        )  # Add a tiny delay to give us enough time to write to the DDS

        self.clock_opll.clock_OPLL_offset.set(
            start_opll_offset
            + self.calculate_frequency_for_first_pi_by_2_pulse(
                t_pulse_start_mu=t_start_last_pulse_mu, t_pi_pulse=t_pi_down
            )
            + last_bs_freq
            + 3 * 9.4e3
        )
        delay_mu(8)

        self.clock_down_dds.set(
            frequency=self.clock_switch_frequency_handle.get()
            + self.down_switch_detuning.get(),
            amplitude=self.clock_switch_amplitude_handle.get(),
            phase=self.calculate_phase_for_second_pi_by_2_pulse(),
        )

        delay(1e-6)

        # PI/2 PULSE

        self.clock_down_dds.sw.on()
        delay(t_pi_down / 2)
        self.clock_down_dds.sw.off()

    @kernel
    def do_selective_lmt_pulse(self, detuning, N_kicks, duration):
        self.clock_up_dds.set_att(13.0)

        delay_mu(8)
        t_pulse = now_mu() + self.core.seconds_to_mu(1e-6)

        opll_frequency = (
            start_opll_offset
            + self.calculate_frequency_for_selective_lmt_pulse(
                t_pulse_start_mu=t_pulse, N_kicks=N_kicks
            )
            + detuning
        )

        # ramp the offset upwards
        at_mu(t_pulse)
        self.clock_opll.clock_frequency_ramper.start_ramp(
            ramp_rate,
            opll_frequency,
            opll_frequency + 2e6,
            wave_type=1,
        )
        delay_mu(8)

        self.clock_up_dds.sw.on()
        delay(duration)
        self.clock_up_dds.sw.off()
        self.clock_opll.clock_frequency_ramper.stop_ramp()
        self.clock_opll.clock_OPLL_offset.set(80e6)
        self.clock_up_dds.set_att(0.0)


class ShapedFirstPulseLMTInterferometryMixin(LMTInterferometryMixin):
    """
    Implements LMT interferometry after the launch, starting with a Jesse pulse

    Kernel hooks used (multiple mixins cannot use the same hooks):

    * :meth:`~do_experiment_after_dipole_trap`
    """

    def build_fragment(self):
        super().build_fragment()

        self.setattr_fragment(
            "first_lmt_shaped_pulse",
            JessePulse,
            ad9910_name=CLOCK_UP_BEAM_INFO.urukul_device,
        )
        self.first_lmt_shaped_pulse: JessePulse

        self.first_lmt_shaped_pulse.bind_param(
            "pulse_duration", self.first_lmt_duration
        )

    @kernel
    def do_selective_lmt_pulse(self, detuning, N_kicks, duration):

        # prepare ram mode
        self.first_lmt_shaped_pulse.prepare_pulse(
            frequency=CLOCK_UP_BEAM_INFO.frequency
        )
        delay_mu(int64(self.core.ref_multiplier))

        t_pulse = now_mu() + self.core.seconds_to_mu(1e-6)

        # set the frequency on the opll
        opll_frequency = (
            start_opll_offset
            + self.calculate_frequency_for_selective_lmt_pulse(
                t_pulse_start_mu=t_pulse, N_kicks=N_kicks
            )
            + detuning
        )

        at_mu(t_pulse)
        # ramp the offset upwards
        self.clock_opll.clock_frequency_ramper.start_ramp(
            ramp_rate,
            opll_frequency,
            opll_frequency + 2e6,
            wave_type=1,
        )

        # pulse
        self.first_lmt_shaped_pulse.trigger_pulse()

        # disable ram mode after shelving and clearout
        self.first_lmt_shaped_pulse.disable_ram_mode()
        # re-set the AOM to default
        self.clock_default_setter._turn_on_ad9910s(light_enabled=False)

        # stop the frequency ramp
        self.clock_opll.clock_frequency_ramper.stop_ramp()
        self.clock_opll.clock_OPLL_offset.set(80e6)
