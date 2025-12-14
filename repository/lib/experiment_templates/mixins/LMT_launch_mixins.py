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

        self.setattr_param(
            "down_offset_detuning",
            FloatParam,
            "Extra detuning for up beam",
            default=constants.LMT_DOWN_BEAM_RECOIL_SHIFT,
            unit="kHz",
        )
        self.down_offset_detuning: FloatParamHandle

        if not hasattr(self, "clock_opll"):
            self.setattr_fragment("clock_opll", ClockOPLLController)
            self.clock_opll: ClockOPLLController

    # use if we start in the excited state
    @kernel
    def lmt_series(self, offset_det, N):

        kick = self.momentum_kick.get()
        total_ramp_time = 0.0

        t_start_ramp = now_mu()
        for i in range(N):

            if i % 2 == 0:
                down_offset = 0.0
            else:
                down_offset = -15e3  # self.down_offset_detuning.get()

            f_i = (
                start_opll_offset
                + (-1) ** (i + 1) * total_ramp_time * ramp_rate
                + i * (-1) ** (i) * kick
                + (-1) ** i * (offset_det + down_offset)
            )
            # start with down pulse
            if i % 2 == 0:
                pulse_type = "down"

            else:
                pulse_type = "up"

            # fire the pulse
            self.fire_lmt_pulse(f_i, pulse_type)

            # Clear out the ground state
            # if pulse_type == "up":
            #     self.fluorescence_pulse.do_imaging_pulse(
            #         duration=self.clearout_duration.get(),
            #         ignore_final_shutters=True,
            #     )
            #     delay(8e-9)

            t_end_pulse = now_mu()
            total_ramp_time = self.core.mu_to_seconds(t_end_pulse - t_start_ramp)

    # use if we start in the ground state
    @kernel
    def lmt_series_start_up(self, offset_det, offset_down_beam, N):
        kick = self.momentum_kick.get()
        total_ramp_time = 0.0

        t_start_ramp = now_mu()
        for i in range(N):

            # start with up pulse
            if i % 2 == 0:
                down_offset = 0.0
                pulse_type = "up"
            else:
                down_offset = offset_down_beam
                pulse_type = "down"

            f_i = (
                start_opll_offset
                + (-1) ** (i) * total_ramp_time * ramp_rate
                + i * (-1) ** (i + 1) * kick
                + (-1) ** (i + 1) * (offset_det + down_offset)
            )

            # fire the pulse
            self.fire_lmt_pulse(f_i, pulse_type)

            # Clear out the ground state
            # if pulse_type == "down":
            #     self.fluorescence_pulse.do_imaging_pulse(
            #         duration=self.clearout_duration.get(),
            #         ignore_final_shutters=True,
            #     )
            #     delay(8e-9)

            delay(100e-6)
            t_end_pulse = now_mu()
            total_ramp_time = self.core.mu_to_seconds(t_end_pulse - t_start_ramp)

    @kernel
    def lmt_series_start_down_launch_down(self, offset_det, offset_down_beam, N):
        kick = self.momentum_kick.get()
        total_ramp_time = 0.0

        t_start_ramp = now_mu()
        for i in range(N):

            # start with down pulse
            if i % 2 == 0:
                down_offset = 0.0
                pulse_type = "down"
            else:
                down_offset = offset_down_beam
                pulse_type = "up"

            f_i = (
                start_opll_offset
                + (-1) ** (i + 1) * total_ramp_time * ramp_rate
                + i * (-1) ** (i + 1) * kick
                + (-1) ** (i) * (offset_det + down_offset)
            )

            # fire the pulse
            self.fire_lmt_pulse(f_i, pulse_type)

            # delay(100e-6)
            t_end_pulse = now_mu()
            total_ramp_time = self.core.mu_to_seconds(t_end_pulse - t_start_ramp)

    @kernel
    def fire_lmt_pulse(self, start_freq, type):
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
            self.clock_up_dds.sw.on()
            delay(self.spectroscopy_pulse_time.get())
            self.clock_up_dds.sw.off()
        delay(25e-6)

    @kernel
    def calculate_frequency_for_first_lmt_pulse(
        self, t_pulse_start_mu: int64, t_pi_pulse: float
    ) -> float:
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
            "lmt_lauch_offset_detuning",
            FloatParam,
            "LMT offset detuning",
            default=constants.LMT_OFFSET_DETUNING,
            unit="kHz",
        )
        self.lmt_launch_offset_detuning: FloatParamHandle

    @kernel
    def launch_hook(self):
        self.prepare_clock_delivery_aom()
        delay_mu(16)
        start_detuning = self.lmt_launch_offset_detuning.get()
        lmt_number = self.lmt_launch_pulses_number.get()
        self.lmt_series(start_detuning, lmt_number)


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
            "first_lmt_freq",
            FloatParam,
            "Detuning 1st LMT pulse",
            default=0.0,
            unit="kHz",
        )
        self.first_lmt_freq: FloatParamHandle

        self.setattr_param(
            "bs1_lmt_offset_detuning",
            FloatParam,
            "LMT detuning after 1st BS",
            default=-6.5e3,
            unit="kHz",
        )
        self.bs1_lmt_offset_detuning: FloatParamHandle

        self.setattr_param(
            "upper_mirror_offset_detuning",
            FloatParam,
            "LMT detuning for upper arm mirror",
            default=23.5e3,
            unit="kHz",
        )
        self.upper_mirror_offset_detuning: FloatParamHandle

        self.setattr_param(
            "last_upper_mirror_lmt_freq",
            FloatParam,
            "Detuning last upper arm mirror LMT pulse",
            default=39.5e3,
            unit="kHz",
        )
        self.last_upper_mirror_lmt_freq: FloatParamHandle

        self.setattr_param(
            "mirror_pulse_freq",
            FloatParam,
            "Frequency detuning for the mirror pulse",
            default=-40e3,
            unit="kHz",
        )
        self.mirror_pulse_freq: FloatParamHandle

        self.setattr_param(
            "first_lower_mirror_lmt_freq",
            FloatParam,
            "Detuning first lower arm mirror LMT pulse",
            default=40.5e3,
            unit="kHz",
        )
        self.first_lower_mirror_lmt_freq: FloatParamHandle

        self.setattr_param(
            "lower_mirror_offset_detuning",
            FloatParam,
            "LMT detuning for lower arm mirror",
            default=-22.5e3,
            unit="kHz",
        )
        self.lower_mirror_offset_detuning: FloatParamHandle

        self.setattr_param(
            "lower_arm_bs_detuning",
            FloatParam,
            "Detuning BS LMT series on lower arm",
            default=9.5e3,
            unit="kHz",
        )
        self.lower_arm_bs_detuning: FloatParamHandle

        self.setattr_param(
            "last_selective_lower_bs_freq",
            FloatParam,
            "Frequency detuning for last selective lower BS",
            default=55e3,
            unit="kHz",
        )
        self.last_selective_lower_bs_freq: FloatParamHandle

        self.setattr_param(
            "last_bs_freq",
            FloatParam,
            "Frequency detuning for last BS",
            default=-62e3,
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

        t_pi_up = self.spectroscopy_pulse_time.get()
        t_pi_down = self.down_pulses_duration.get()
        t_first_pi = self.first_lmt_duration.get()

        # frequencies
        first_freq = (
            self.first_lmt_freq.get()
        )  # TODO: this is zero, need to delete the parameter
        bs1_lmt_offset = self.bs1_lmt_offset_detuning.get()
        down_offset = self.down_offset_detuning.get()
        upper_mirror_offset = self.upper_mirror_offset_detuning.get()
        last_upper_mirror_freq = self.last_upper_mirror_lmt_freq.get()
        mirror_freq = self.mirror_pulse_freq.get()
        first_lower_mirror_freq = self.first_lower_mirror_lmt_freq.get()
        lower_mirror_offset = self.lower_mirror_offset_detuning.get()
        bs_detuning_lower = self.lower_arm_bs_detuning.get()
        last_selective_lower_bs_freq = self.last_selective_lower_bs_freq.get()
        last_bs_freq = self.last_bs_freq.get()

        t_start_first_pulse_mu = now_mu() + self.core.seconds_to_mu(
            1e-6
        )  # Add a tiny delay to give us enough time to write to the DDS

        self.clock_opll.clock_OPLL_offset.set(
            start_opll_offset
            + self.calculate_frequency_for_first_pi_by_2_pulse(
                t_pulse_start_mu=t_start_first_pulse_mu, t_pi_pulse=t_pi_down
            )
        )
        delay_mu(8)

        self.clock_down_dds.set(
            frequency=self.clock_switch_frequency_handle.get(),
            amplitude=self.clock_switch_amplitude_handle.get(),
            phase=self.calculate_phase_for_first_pi_by_2_pulse(),
        )

        # PI/2 PULSE DOWN BEAM
        at_mu(t_start_first_pulse_mu)
        self.clock_down_dds.sw.on()
        delay(t_pi_down / 2)
        self.clock_down_dds.sw.off()

        delay(500e-6)

        # First pulse with a lower Rabi frequency, up beam pulse
        if N > 1:
            self.do_first_selective_lmt_pulse(first_freq, t_first_pi)

        #     # Clear out the ground state
        #     self.fluorescence_pulse.do_imaging_pulse(
        #         duration=self.clearout_duration.get(),
        #         ignore_final_shutters=True,
        #     )
        #     delay(8e-9)

        # # LMT sequence on upper arm, starting on the excited state at n=2
        # if N > 2:
        #     self.lmt_series(bs1_lmt_offset, N - 2)

        # delay_mu(8)
        # t_end_bs_mu = now_mu()

        # # Do a Stark shifting pulse in the first dark time
        # self.stark_shifter.do_stark_pulse()

        # # dark time
        # t_start_lmt_mirror_mu = t_end_bs_mu + self.core.seconds_to_mu(
        #     self.delay_between_interferometry_pulses.get()
        # )

        # # LMT sequence on upper arm, momentum downwards
        # at_mu(t_start_lmt_mirror_mu)
        # self.lmt_series_start_down_launch_down(upper_mirror_offset, down_offset, N - 2)

        # # Clear out the ground state
        # self.fluorescence_pulse.do_imaging_pulse(
        #     duration=self.clearout_duration.get(),
        #     ignore_final_shutters=True,
        # )
        # delay(8e-9)

        # # last pulse with a lower Rabi frequency, up beam pulse
        # self.do_selective_lmt_pulse(last_upper_mirror_freq, t_first_pi)

        # delay(8e-9)
        # # Phase step
        # self.clock_down_dds.set(
        #     frequency=self.clock_switch_frequency_handle.get(),
        #     amplitude=self.clock_switch_amplitude_handle.get(),
        #     phase=self.calculate_phase_for_pi_pulse(),
        # )

        # # delay to write onto the dds
        # delay(1e-6)

        # # MIRROR PULSE DOWN BEAM
        # self.clock_opll.clock_OPLL_offset.set(start_opll_offset + mirror_freq)
        # delay_mu(8)
        # self.clock_down_dds.sw.on()
        # delay(t_pi_down)
        # self.clock_down_dds.sw.off()

        # delay(1e-6)

        # # first lower arm mirror pulse with a lower Rabi frequency, up beam pulse
        # self.do_selective_lmt_pulse(first_lower_mirror_freq, t_first_pi)

        # # Clear out the ground state
        # self.fluorescence_pulse.do_imaging_pulse(
        #     duration=self.clearout_duration.get(),
        #     ignore_final_shutters=True,
        # )
        # delay(8e-9)

        # # LMT series on lower arm, start from second pulse, down beam
        # self.lmt_series(lower_mirror_offset, N - 2)

        # # Phase step
        # delay_mu(8)

        # delay(self.delay_between_interferometry_pulses.get())

        # # LMT sequence on lower arm, momentum downwards
        # self.lmt_series_start_down_launch_down(bs_detuning_lower, down_offset, N - 2)

        # # Clear out the ground state
        # self.fluorescence_pulse.do_imaging_pulse(
        #     duration=self.clearout_duration.get(),
        #     ignore_final_shutters=True,
        # )
        # delay(8e-9)

        # # last lower arm bs pulse with a lower Rabi frequency, up beam pulse
        # self.do_selective_lmt_pulse(last_selective_lower_bs_freq, t_first_pi)

        # delay(8e-9)

        # self.clock_down_dds.set(
        #     frequency=self.clock_switch_frequency_handle.get(),
        #     amplitude=self.clock_switch_amplitude_handle.get(),
        #     phase=self.calculate_phase_for_second_pi_by_2_pulse(),
        # )

        # delay(500e-6)

        # # PI/2 PULSE
        # self.clock_opll.clock_OPLL_offset.set(start_opll_offset + last_bs_freq)
        # delay_mu(8)

        # self.clock_down_dds.sw.on()
        # delay(t_pi_down / 2)
        # self.clock_down_dds.sw.off()

    @kernel
    def do_first_selective_lmt_pulse(self, freq, duration):
        self.clock_up_dds.set_att(13.0)

        delay_mu(8)
        t_pulse = now_mu() + self.core.seconds_to_mu(1e-6)

        opll_frequency = (
            start_opll_offset
            + self.calculate_frequency_for_first_lmt_pulse(
                t_pulse_start_mu=t_pulse, t_pi_pulse=duration
            )
            + self.first_lmt_freq.get()
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

    @kernel
    def do_selective_lmt_pulse(self, freq, duration):
        self.clock_up_dds.set_att(13.0)

        delay_mu(8)
        t_pulse = now_mu() + self.core.seconds_to_mu(1e-6)

        opll_frequency = start_opll_offset + freq

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
    def do_selective_lmt_pulse(self, freq, duration):

        # prepare ram mode
        self.first_lmt_shaped_pulse.prepare_pulse(
            frequency=CLOCK_UP_BEAM_INFO.frequency
        )
        delay_mu(int64(self.core.ref_multiplier))

        # set the frequency on the opll
        self.clock_opll.clock_OPLL_offset.set(start_opll_offset + freq)
        # ramp the offset upwards
        self.clock_opll.clock_frequency_ramper.start_ramp(
            ramp_rate,
            start_opll_offset + freq,
            start_opll_offset + freq + 2e6,
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
