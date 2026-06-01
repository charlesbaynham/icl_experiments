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
from numpy import int32
from numpy import int64
from pyaion.models import SUServoedBeam
from pyaion.models import UrukuledBeam

from repository.lib import constants
from repository.lib.experiment_templates.dipole_trap_experiment import (
    DipoleTrapWithExperimentBase,
)
from repository.lib.experiment_templates.mixins.clock_interferometry import (
    ClockInterferometryBase,
)
from repository.lib.experiment_templates.mixins.clock_spectroscopy import (
    ClockSpectroscopyBase,
)
from repository.lib.experiment_templates.red_mot_experiment import (
    RedMOTWithExperimentBase,
)
from repository.lib.fragments.clock_opll_controller import ClockOPLLController
from repository.lib.fragments.pulse_shaping import JessePulseLMT
from repository.lib.fragments.pulse_shaping import JessePulseLMTSeries
from repository.lib.fragments.pulse_shaping import JessePulseLMTSeriesDown

CLOCK_UP_BEAM_INFO: UrukuledBeam = constants.URUKULED_BEAMS["clock_up"]
CLOCK_DOWN_BEAM_INFO: UrukuledBeam = constants.URUKULED_BEAMS["clock_down"]
CLOCK_BEAM_DELIVERY_INFO: SUServoedBeam = constants.SUSERVOED_BEAMS["clock_delivery"]

ramp_rate = constants.GRAVITY_DOPPLER_PER_SEC_CLOCK
momentum_kick = constants.MOMENTUM_KICK_DETUNING
start_opll_offset = 80e6

logger = logging.getLogger(__name__)


class LMTBase(
    ClockSpectroscopyBase,
    RedMOTWithExperimentBase,
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
            default=1.5e3,
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
        self.clearout_duration: FloatParamHandle

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

        if not hasattr(self, "clock_opll"):
            self.setattr_fragment("clock_opll", ClockOPLLController)
            self.clock_opll: ClockOPLLController

    # ------------------------------------------------------------------
    # OPLL command wrappers. Thin wrappers around the clock_opll DDS /
    # ramper that also update the frequency-tracking state read by
    # PulseDMARecording.register_pulse, so call sites never have to track
    # the OPLL frequency separately.
    # ------------------------------------------------------------------

    @kernel
    def set_clock_opll(self, freq: float):
        """Set the OPLL offset DDS to a static frequency (and track it)."""
        self.clock_opll.clock_OPLL_offset.set(freq)
        self._tracked_opll_freq = freq
        self._tracked_opll_ramp_active = False

    @kernel
    def start_clock_opll_ramp(
        self,
        rate: float,
        freq_low: float,
        freq_high: float,
        wave_type: int32,
    ):
        """Start a DRG ramp on the OPLL offset DDS (and track it)."""
        self.clock_opll.clock_frequency_ramper.start_ramp(
            rate, freq_low, freq_high, wave_type=wave_type
        )
        self._tracked_opll_ramp_rate = rate
        self._tracked_opll_ramp_low = freq_low
        self._tracked_opll_ramp_high = freq_high
        self._tracked_opll_ramp_wave = wave_type
        self._tracked_opll_ramp_start_mu = now_mu()
        self._tracked_opll_ramp_active = True

    @kernel
    def stop_clock_opll_ramp(self):
        """Stop the OPLL DRG ramp (and track that it is no longer active)."""
        self.clock_opll.clock_frequency_ramper.stop_ramp()
        self._tracked_opll_ramp_active = False

    # use if we start in the excited state
    @kernel
    def lmt_series(self, offset_det, N_previous_pulses, N):

        t_drop = self.get_t_start_shelving()

        for i in range(N):

            if i % 2 == 0:
                down_offset = offset_det
                pulse_type = "down"
            else:
                down_offset = 0.0
                pulse_type = "up"

            t_start_lmt_pulse_mu = now_mu() + self.core.seconds_to_mu(50e-6)
            total_ramp_time = self.core.mu_to_seconds(t_start_lmt_pulse_mu - t_drop)

            f_i = (
                start_opll_offset
                + (-1) ** (i + 1) * total_ramp_time * ramp_rate
                + (i + N_previous_pulses) * (-1) ** (i) * momentum_kick
                + (-1) ** i * down_offset
            )

            # fire the pulse
            self.fire_lmt_pulse(f_i, pulse_type, t_start_lmt_pulse_mu)

    @kernel
    def launch_series(self, offset_det, N_previous_pulses, N):

        t_drop = self.get_t_start_shelving()

        for i in range(N):

            if i % 2 == 0:
                pulse_type = "down"
                down_offset = offset_det
            else:
                pulse_type = "up"
                down_offset = 0.0

            t_start_lmt_pulse_mu = now_mu() + self.core.seconds_to_mu(2e-6)
            total_ramp_time = self.core.mu_to_seconds(t_start_lmt_pulse_mu - t_drop)

            f_i = (
                start_opll_offset
                + (-1) ** (i + 1) * total_ramp_time * ramp_rate
                + (i + N_previous_pulses) * (-1) ** (i) * momentum_kick
                + (-1) ** i * down_offset
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

        t_drop = self.get_t_start_shelving()

        for i in range(N):

            # start with up pulse
            if i % 2 == 0:
                down_offset = offset_det
                pulse_type = "up"
            else:
                down_offset = 0.0
                pulse_type = "down"

            t_start_lmt_pulse_mu = now_mu() + self.core.seconds_to_mu(2e-6)
            total_ramp_time = self.core.mu_to_seconds(t_start_lmt_pulse_mu - t_drop)

            f_i = (
                start_opll_offset
                + (-1) ** (i) * total_ramp_time * ramp_rate
                + (i + N_previous_pulses) * (-1) ** (i + 1) * momentum_kick
                + (-1) ** (i + 1) * down_offset
            )

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
        t_drop = self.get_t_start_shelving()

        for i in range(N):

            # start with down pulse
            if i % 2 == 0:
                down_offset = offset_det
                pulse_type = "down"

            else:
                down_offset = 0.0
                pulse_type = "up"

            t_start_lmt_2_pulse_mu = now_mu() + self.core.seconds_to_mu(50e-6)
            total_ramp_time = self.core.mu_to_seconds(t_start_lmt_2_pulse_mu - t_drop)

            f_i = (
                start_opll_offset
                + (-1) ** (i + 1) * total_ramp_time * ramp_rate
                + i * (-1) ** (i + 1) * momentum_kick
                + N_previous_pulses * (-1) ** (i) * momentum_kick
                + (-1) ** (i) * (down_offset)
            )

            # fire the pulse
            self.fire_lmt_pulse(f_i, pulse_type, t_start=t_start_lmt_2_pulse_mu)

    @kernel
    def lmt_series_start_down_launch_down_v2(self, offset_det, N_previous_pulses, N):
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
                + i * (-1) ** (i + 1) * momentum_kick
                + N_previous_pulses * (-1) ** (i) * momentum_kick
                + (-1) ** (i) * (down_offset)
            )

            # fire the pulse
            self.fire_lmt_pulse(f_i, pulse_type, t_start=t_start_lmt_2_pulse_mu)

            if pulse_type == "down":
                # Clear out the ground state
                self.fluorescence_pulse.do_clearout_pulse(
                    duration=10e-6,
                    ignore_final_shutters=True,
                )
                delay(8e-9)

    @kernel
    def fire_lmt_pulse(self, start_freq, type, t_start):
        # stop the ramp
        self.stop_clock_opll_ramp()
        # set the offset frequency
        self.set_clock_opll(start_freq)

        if type == "down":
            at_mu(t_start)
            # ramp the offset downwards
            # self.clock_opll.clock_frequency_ramper.start_ramp(
            #     ramp_rate,
            #     start_freq - 1e6,
            #     start_freq,
            #     wave_type=2,
            # )
            # delay_mu(8)
            # pulse the down beam

            d = self.down_pulses_duration.get()
            self.register_pulse(duration_s=d, is_up=False)
            self.clock_down_dds.sw.on()
            delay(d)
            self.clock_down_dds.sw.off()

        if type == "up":
            at_mu(t_start)
            # ramp the offset upwards
            # self.clock_opll.clock_frequency_ramper.start_ramp(
            #     ramp_rate,
            #     start_freq,
            #     start_freq + 2e6,
            #     wave_type=1,
            # )
            # delay_mu(8)

            # pulse the up beam

            d = self.spectroscopy_pulse_time.get()
            self.register_pulse(duration_s=d, is_up=True)
            self.clock_up_dds.sw.on()
            delay(d)
            self.clock_up_dds.sw.off()
        delay(10e-6)

    @kernel
    def do_selective_lmt_pulse(self, detuning, N_kicks, att, duration):
        self.clock_up_dds.set_att(att)

        delay_mu(8)
        t_pulse = now_mu() + self.core.seconds_to_mu(50e-6)

        opll_frequency = (
            start_opll_offset
            + self.calculate_frequency_for_selective_lmt_pulse(
                t_pulse_start_mu=t_pulse, N_kicks=N_kicks
            )
            + detuning
        )

        # ramp the offset upwards
        at_mu(t_pulse)
        self.start_clock_opll_ramp(
            ramp_rate,
            opll_frequency,
            opll_frequency + 2e6,
            wave_type=1,
        )
        delay_mu(8)

        d = duration
        self.register_pulse(duration_s=d, is_up=True)
        self.clock_up_dds.sw.on()
        delay(d)
        self.clock_up_dds.sw.off()
        self.stop_clock_opll_ramp()
        self.set_clock_opll(80e6)
        self.clock_up_dds.set_att(0.0)

    @kernel
    def do_selective_lmt_pulse_down_beam(self, detuning, N_kicks, att, duration):
        self.clock_down_dds.set_att(att)

        delay_mu(8)
        t_pulse = now_mu() + self.core.seconds_to_mu(1e-6)

        opll_frequency = (
            start_opll_offset
            - self.calculate_frequency_for_selective_lmt_pulse(
                t_pulse_start_mu=t_pulse, N_kicks=N_kicks
            )
            + detuning
        )

        # ramp the offset upwards
        at_mu(t_pulse)
        self.start_clock_opll_ramp(
            ramp_rate,
            opll_frequency - 1e6,
            opll_frequency,
            wave_type=2,
        )
        delay_mu(8)

        d = duration
        self.register_pulse(duration_s=d, is_up=False)
        self.clock_down_dds.sw.on()
        delay(d)
        self.clock_down_dds.sw.off()
        self.stop_clock_opll_ramp()
        self.set_clock_opll(80e6)
        self.clock_down_dds.set_att(0.0)

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
        return 0


class LMTLaunchMixin(LMTBase, DipoleTrapWithExperimentBase):
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
            default=16,
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

        self.set_clock_down_dds(
            frequency=self.clock_switch_frequency_handle.get()
            + self.down_switch_detuning.get(),
            amplitude=self.clock_switch_amplitude_handle.get(),
        )

        self.set_clock_up_dds(
            frequency=self.clock_switch_frequency_handle.get()
            + self.up_switch_detuning_higher_intensity.get(),
            amplitude=self.clock_switch_amplitude_handle.get(),
        )
        self.launch_hook_default()

    @kernel
    def launch_hook_default(self):
        delay_mu(16)
        start_detuning = self.lmt_launch_offset_detuning.get()
        lmt_number = self.lmt_launch_pulses_number.get()

        self.launch_series(start_detuning, N_previous_pulses=1, N=lmt_number)
        # # Clear out the ground state
        # self.fluorescence_pulse.do_imaging_pulse(
        #     duration=50e-6,  # self.clearout_duration.get(),
        #     ignore_final_shutters=True,
        # )
        # delay_mu(8)

        # delay_mu(8)
        # self.clock_opll.clock_frequency_ramper.start_ramp(
        #     ramp_rate,
        #     80e6 - 1e6,
        #     80e6,
        #     wave_type=2,
        # )

        delay(10e-6)


class LMTLaunchDoubleTrapMixin(LMTLaunchMixin, DipoleTrapWithExperimentBase):
    """
    Implements LMT launch after the dipole trap to create a double trap

    Kernel hooks used (multiple mixins cannot use the same hooks):

    * :meth:`~launch_hook`
    """

    def build_fragment(self):
        super().build_fragment()

        self.setattr_param(
            "delay_between_launches",
            FloatParam,
            "Delay between the two launches",
            default=2.0e-3,
            unit="ms",
        )
        self.delay_between_launches: FloatParamHandle

        self.setattr_param(
            "double_trap_launch_bs_detuning",
            FloatParam,
            "Detuning of the beam splitter in the double trap launch",
            default=1.0e3,  # -0.3e3,
            unit="kHz",
        )
        self.double_trap_launch_bs_detuning: FloatParamHandle

        self.setattr_param_rebind(
            "lmt_launch_offset_detuning_double_cloud",
            self,
            original_name="lmt_launch_offset_detuning",
            description="Detuning for launch LMT series",
            default=0.2e3,
        )
        self.lmt_launch_offset_detuning_double_cloud: FloatParamHandle

        self.setattr_param(
            "launch_upper_selective_cloud_detuning",
            FloatParam,
            "Detuning of selective pulse upper cloud launch",
            default=-0.3e3,
            unit="kHz",
        )
        self.launch_upper_selective_cloud_detuning: FloatParamHandle

        self.setattr_param(
            "launch_lower_selective_cloud_detuning",
            FloatParam,
            "Detuning of selective pulse lower cloud launch",
            default=4.5e3,
            unit="kHz",
        )
        self.launch_lower_selective_cloud_detuning: FloatParamHandle

        self.setattr_param(
            "double_launch_last_pulse_detuning",
            FloatParam,
            "Detuning of the last pulse of double launch",
            default=3.0e3,
            unit="kHz",
        )
        self.double_launch_last_pulse_detuning: FloatParamHandle

    @kernel
    def launch_hook(self):
        self.launch_hook_double_cloud()

    @kernel
    def launch_hook_double_cloud(self):
        self.prepare_clock_delivery_aom()
        delay_mu(16)

        t_pi_down = self.down_pulses_duration.get()
        t_pi_up = self.spectroscopy_pulse_time.get()

        lmt_detuning = self.lmt_launch_offset_detuning_double_cloud.get()
        N_launch = self.lmt_launch_pulses_number.get()
        upper_selective_det = self.launch_upper_selective_cloud_detuning.get()
        lower_selective_det = self.launch_lower_selective_cloud_detuning.get()
        last_detuning = self.double_launch_last_pulse_detuning.get()

        self.stop_clock_opll_ramp()
        delay_mu(8)

        t_start_first_pulse_mu = now_mu() + self.core.seconds_to_mu(2e-6)
        self.set_clock_opll(
            start_opll_offset
            + self.calculate_frequency_for_first_pi_by_2_pulse(
                t_pulse_start_mu=t_start_first_pulse_mu,
                t_pi_pulse=t_pi_down,
            )
            + self.double_trap_launch_bs_detuning.get()
        )

        self.set_clock_down_dds(
            frequency=self.clock_switch_frequency_handle.get()
            + self.down_switch_detuning.get(),
            amplitude=self.clock_switch_amplitude_handle.get(),
        )

        # PI/2 PULSE DOWN BEAM
        at_mu(t_start_first_pulse_mu)
        d = t_pi_down / 2
        self.register_pulse(duration_s=d, is_up=False)
        self.clock_down_dds.sw.on()
        delay(d)
        self.clock_down_dds.sw.off()

        # LMT series on the upper trap
        self.set_clock_up_dds(
            frequency=self.clock_switch_frequency_handle.get()
            + self.up_switch_detuning_lower_intensity.get(),
            amplitude=self.clock_switch_amplitude_handle.get(),
        )

        delay(1e-6)

        # First pulse with a lower Rabi frequency, up beam pulse
        self.do_selective_lmt_pulse(
            upper_selective_det, N_kicks=2, att=10.5, duration=95e-6
        )

        # Clear out the ground state
        self.fluorescence_pulse.do_imaging_pulse(
            duration=self.clearout_duration.get(),
            ignore_final_shutters=True,
        )
        delay(8e-9)

        # # second pulse with a lower Rabi frequency, down beam pulse
        # self.do_selective_lmt_pulse_down_beam(
        #     -2.0e3, N_kicks=3, att=9.5, duration=50e-6
        # )
        # delay(8e-9)

        # # Third pulse with a lower Rabi frequency, up beam pulse
        # self.do_selective_lmt_pulse(1.0e3, N_kicks=4, att=6.0, duration=51e-6)
        # delay(8e-9)

        self.set_clock_up_dds(
            frequency=self.clock_switch_frequency_handle.get()
            + self.up_switch_detuning_higher_intensity.get(),
            amplitude=self.clock_switch_amplitude_handle.get(),
        )
        delay(8e-9)

        # LMT sequence on upper trap
        self.lmt_series(1.0e3, N_previous_pulses=3, N=N_launch - 2)

        delay(1e-6)
        self.set_clock_opll(80e6)
        delay(100e-6)
        # Clear out the ground state
        self.fluorescence_pulse.do_imaging_pulse(
            duration=self.clearout_duration.get(),
            ignore_final_shutters=True,
        )

        delay(self.delay_between_launches.get())

        # LMT series on the lower trap
        self.lmt_series(lmt_detuning, N_previous_pulses=1, N=N_launch - 2)

        self.set_clock_up_dds(
            frequency=self.clock_switch_frequency_handle.get()
            + self.up_switch_detuning_lower_intensity.get(),
            amplitude=self.clock_switch_amplitude_handle.get(),
        )

        delay_mu(8)

        # Clear out the ground state
        self.fluorescence_pulse.do_imaging_pulse(
            duration=self.clearout_duration.get(),
            ignore_final_shutters=True,
        )

        # # pulse with a lower Rabi frequency, down beam pulse
        # self.do_selective_lmt_pulse_down_beam(
        #     0.0, N_kicks=N_launch - 2 + 1, att=0.0, duration=32e-6
        # )
        # delay(8e-9)

        # # pulse with a lower Rabi frequency, up beam pulse
        # self.do_selective_lmt_pulse(
        #     0.0, N_kicks=N_launch - 1 + 1, att=1.0, duration=47e-6
        # )
        # delay(8e-9)

        # second before last pulse with a lower Rabi frequency, down beam pulse
        self.do_selective_lmt_pulse_down_beam(
            lower_selective_det, N_kicks=int(N_launch) - 2 + 1, att=0.0, duration=95e-6
        )

        delay(1e-6)
        self.set_clock_opll(80019941.0)

        # last pulse, pi/2 with up beam and then throw away ground state
        t_start_last_pulse_mu = now_mu() + self.core.seconds_to_mu(1e-6)
        self.set_clock_opll(
            start_opll_offset
            - self.calculate_frequency_for_first_pi_by_2_pulse(
                t_pulse_start_mu=t_start_last_pulse_mu, t_pi_pulse=t_pi_down
            )
            + last_detuning
            - (N_launch + 1 - 2) * momentum_kick
        )

        delay(8e-9)

        at_mu(t_start_last_pulse_mu)
        d = t_pi_up / 2
        self.register_pulse(duration_s=d, is_up=True)
        self.clock_up_dds.sw.on()
        delay(d)
        self.clock_up_dds.sw.off()

        delay(1e-6)

        # # Clear out the ground state
        # self.fluorescence_pulse.do_imaging_pulse(
        #     duration=200e-6,
        #     ignore_final_shutters=True,
        # )


class LMTLaunchDoubleTrapShapedPulseMixin(LMTLaunchMixin, DipoleTrapWithExperimentBase):
    """
    Implements LMT launch after the dipole trap to create a double trap. Uses a shaped pulse to
    address both clouds, with opposite momentum, after the beam splitter.

    Kernel hooks used (multiple mixins cannot use the same hooks):

    * :meth:`~launch_hook`
    """

    def build_fragment(self):
        super().build_fragment()

        self.setattr_fragment(
            "first_lmt_shaped_pulse",
            JessePulseLMT,
            ad9910_name=CLOCK_UP_BEAM_INFO.urukul_device,
        )
        self.first_lmt_shaped_pulse: JessePulseLMT

        self.setattr_param_rebind(
            "shaped_pulse_duration",
            self.first_lmt_shaped_pulse,
            "pulse_duration",
            default=200e-6,
            description="Duration of the Jesse pulse",
        )

        self.setattr_param(
            "delay_between_launches",
            FloatParam,
            "Delay between the two launches",
            default=2.0e-3,
            unit="ms",
        )
        self.delay_between_launches: FloatParamHandle

        self.setattr_param(
            "double_trap_launch_bs_detuning",
            FloatParam,
            "Detuning of the beam splitter in the double trap launch",
            default=1e3,
            unit="kHz",
        )
        self.double_trap_launch_bs_detuning: FloatParamHandle

        self.setattr_param_rebind(
            "lmt_launch_offset_detuning_double_cloud",
            self,
            original_name="lmt_launch_offset_detuning",
            description="Detuning for launch LMT series",
            default=0.2e3,
        )
        self.lmt_launch_offset_detuning_double_cloud: FloatParamHandle

        self.setattr_param(
            "launch_upper_selective_cloud_detuning",
            FloatParam,
            "Detuning of selective pulse upper cloud launch",
            default=10.0e3,
            unit="kHz",
        )
        self.launch_upper_selective_cloud_detuning: FloatParamHandle

        self.setattr_param(
            "launch_lower_selective_cloud_detuning",
            FloatParam,
            "Detuning of selective pulse lower cloud launch",
            default=0e3,
            unit="kHz",
        )
        self.launch_lower_selective_cloud_detuning: FloatParamHandle

        self.setattr_param(
            "double_launch_last_pulse_detuning",
            FloatParam,
            "Detuning of the last pulse of double launch",
            default=0.5e3,
            unit="kHz",
        )
        self.double_launch_last_pulse_detuning: FloatParamHandle

    @kernel
    def launch_hook(self):
        self.launch_hook_double_cloud()

    @kernel
    def launch_hook_double_cloud(self):
        self.prepare_clock_delivery_aom()
        delay_mu(16)

        t_pi_down = self.down_pulses_duration.get()
        t_pi_up = self.spectroscopy_pulse_time.get()

        lmt_detuning = self.lmt_launch_offset_detuning_double_cloud.get()
        N_launch = self.lmt_launch_pulses_number.get()
        self.launch_upper_selective_cloud_detuning.get()
        lower_selective_det = self.launch_lower_selective_cloud_detuning.get()
        last_detuning = self.double_launch_last_pulse_detuning.get()

        self.stop_clock_opll_ramp()
        delay_mu(8)

        t_start_first_pulse_mu = now_mu() + self.core.seconds_to_mu(2e-6)
        self.set_clock_opll(
            start_opll_offset
            + self.calculate_frequency_for_first_pi_by_2_pulse(
                t_pulse_start_mu=t_start_first_pulse_mu,
                t_pi_pulse=t_pi_down,
            )
            + self.double_trap_launch_bs_detuning.get()
        )

        self.set_clock_down_dds(
            frequency=self.clock_switch_frequency_handle.get()
            + self.down_switch_detuning.get(),
            amplitude=self.clock_switch_amplitude_handle.get(),
        )

        # PI/2 PULSE DOWN BEAM
        at_mu(t_start_first_pulse_mu)
        d = t_pi_down / 2
        self.register_pulse(duration_s=d, is_up=False)
        self.clock_down_dds.sw.on()
        delay(d)
        self.clock_down_dds.sw.off()

        # Shaped pulse with up beam, common to both clouds
        self.first_shaped_lmt_pulse(detuning=2.0e3, N_kicks=1)

        self.set_clock_up_dds(
            frequency=self.clock_switch_frequency_handle.get()
            + self.up_switch_detuning_higher_intensity.get(),
            amplitude=self.clock_switch_amplitude_handle.get(),
        )
        delay(8e-9)

        # LMT sequence on upper trap

        self.lmt_series(lmt_detuning, N_previous_pulses=3, N=N_launch)

        delay(self.delay_between_launches.get())

        # LMT series on the lower trap
        self.lmt_series_start_up(
            lower_selective_det, N_previous_pulses=0, N=N_launch + 2
        )

        self.set_clock_up_dds(
            frequency=self.clock_switch_frequency_handle.get()
            + self.up_switch_detuning_lower_intensity.get(),
            amplitude=self.clock_switch_amplitude_handle.get(),
        )

        delay_mu(8)

        delay(8e-9)

        # # last pulse, pi/2 with up beam and then throw away ground state
        t_start_last_pulse_mu = now_mu() + self.core.seconds_to_mu(1e-6)

        opll_frequency = (
            start_opll_offset
            - self.calculate_frequency_for_first_pi_by_2_pulse(
                t_pulse_start_mu=t_start_last_pulse_mu, t_pi_pulse=t_pi_up
            )
            + last_detuning
            - (N_launch + 1) * momentum_kick
        )

        # ramp the offset upwards
        at_mu(t_start_last_pulse_mu)
        self.start_clock_opll_ramp(
            ramp_rate,
            opll_frequency,
            opll_frequency + 2e6,
            wave_type=1,
        )

        d = t_pi_up / 1.8
        self.register_pulse(duration_s=d, is_up=True)
        self.clock_up_dds.sw.on()
        delay(d)
        self.clock_up_dds.sw.off()
        self.stop_clock_opll_ramp()
        self.set_clock_opll(80e6)

        delay(1e-6)

        # Clear out the ground state
        self.fluorescence_pulse.do_clearout_pulse(
            duration=200e-6,
            ignore_final_shutters=True,
        )

    @kernel
    def first_shaped_lmt_pulse(self, detuning, N_kicks):
        self.set_clock_up_dds(
            frequency=self.clock_switch_frequency_handle.get()
            + self.up_switch_detuning_higher_intensity.get(),
            amplitude=self.clock_switch_amplitude_handle.get(),
        )

        # prepare ram mode
        self.first_lmt_shaped_pulse.prepare_pulse(
            frequency=CLOCK_UP_BEAM_INFO.frequency
        )
        delay_mu(int64(self.core.ref_multiplier))
        self.clock_up_dds.set_att(0.0)
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
        self.start_clock_opll_ramp(
            ramp_rate,
            opll_frequency,
            opll_frequency + 2e6,
            wave_type=1,
        )

        # pulse
        self.first_lmt_shaped_pulse.trigger_pulse()

        # stop the frequency ramp
        self.stop_clock_opll_ramp()

        # disable ram mode
        self.first_lmt_shaped_pulse.disable_ram_mode()
        # re-set the AOM to default
        self.clock_default_setter._turn_on_ad9910s(light_enabled=False)


class LMTLaunchDoubleTrapTwoShapedPulsesMixin(
    LMTLaunchMixin, DipoleTrapWithExperimentBase
):
    """
    Implements LMT launch after the dipole trap to create a double trap. Uses a shaped pulse to
    address both clouds, with opposite momentum, after the beam splitter, and shaped pulses for the LMT series

    Kernel hooks used (multiple mixins cannot use the same hooks):

    * :meth:`~launch_hook`
    """

    def build_fragment(self):
        super().build_fragment()

        self.setattr_fragment(
            "first_lmt_shaped_pulse",
            JessePulseLMT,
            ad9910_name=CLOCK_UP_BEAM_INFO.urukul_device,
        )
        self.first_lmt_shaped_pulse: JessePulseLMT

        self.setattr_fragment(
            "lmt_series_shaped_pulse_up",
            JessePulseLMTSeries,
            ad9910_name=CLOCK_UP_BEAM_INFO.urukul_device,
        )
        self.lmt_series_shaped_pulse_up: JessePulseLMTSeries

        self.setattr_fragment(
            "lmt_series_shaped_pulse_down",
            JessePulseLMTSeriesDown,
            ad9910_name=CLOCK_DOWN_BEAM_INFO.urukul_device,
        )
        self.lmt_series_shaped_pulse_down: JessePulseLMTSeriesDown

        self.setattr_param_rebind(
            "shaped_pulse_duration",
            self.first_lmt_shaped_pulse,
            "pulse_duration",
            default=200e-6,
            description="Duration of the Jesse pulse",
        )

        self.setattr_param_rebind(
            "shaped_up_pulse_duration",
            self.lmt_series_shaped_pulse_up,
            "pulse_duration",
            default=90e-6,
            description="Duration of the LMT Jesse pulse up",
        )

        self.setattr_param_rebind(
            "shaped_down_pulse_duration",
            self.lmt_series_shaped_pulse_down,
            "pulse_duration",
            default=90e-6,
            description="Duration of the LMT Jesse pulse down",
        )

        self.setattr_param(
            "delay_between_launches",
            FloatParam,
            "Delay between the two launches",
            default=2.0e-3,
            unit="ms",
        )
        self.delay_between_launches: FloatParamHandle

        self.setattr_param(
            "double_trap_launch_bs_detuning",
            FloatParam,
            "Detuning of the beam splitter in the double trap launch",
            default=1e3,
            unit="kHz",
        )
        self.double_trap_launch_bs_detuning: FloatParamHandle

        self.setattr_param_rebind(
            "lmt_launch_offset_detuning_double_cloud",
            self,
            original_name="lmt_launch_offset_detuning",
            description="Detuning for launch LMT series",
            default=0.2e3,
        )
        self.lmt_launch_offset_detuning_double_cloud: FloatParamHandle

        self.setattr_param(
            "launch_upper_selective_cloud_detuning",
            FloatParam,
            "Detuning of selective pulse upper cloud launch",
            default=2.0e3,
            unit="kHz",
        )
        self.launch_upper_selective_cloud_detuning: FloatParamHandle

        self.setattr_param(
            "launch_lower_selective_cloud_detuning",
            FloatParam,
            "Detuning of selective pulse lower cloud launch",
            default=4.5e3,
            unit="kHz",
        )
        self.launch_lower_selective_cloud_detuning: FloatParamHandle

        self.setattr_param(
            "double_launch_last_pulse_detuning",
            FloatParam,
            "Detuning of the last pulse of double launch",
            default=3.0e3,
            unit="kHz",
        )
        self.double_launch_last_pulse_detuning: FloatParamHandle

    @kernel
    def launch_hook(self):
        self.launch_hook_double_cloud()

    @kernel
    def fire_shaped_lmt_pulse(self, start_freq, type, t_start):
        # stop the ramp
        self.stop_clock_opll_ramp()

        # set the offset frequency
        self.set_clock_opll(start_freq)

        if type == "down":
            # ramp the offset downwards
            self.start_clock_opll_ramp(
                ramp_rate,
                start_freq - 1e6,
                start_freq,
                wave_type=2,
            )
            delay_mu(8)
            # pulse the down beam
            at_mu(t_start)
            d = self.lmt_series_shaped_pulse_down.pulse_duration.get()
            # TODO: Track shaped-pulse metadata separately instead of
            # recording these as ordinary square pulses.
            self.register_pulse(duration_s=d, is_up=False)
            self.lmt_series_shaped_pulse_down.trigger_pulse()

        if type == "up":
            # ramp the offset upwards
            self.start_clock_opll_ramp(
                ramp_rate,
                start_freq,
                start_freq + 2e6,
                wave_type=1,
            )
            delay_mu(8)

            # pulse the up beam
            at_mu(t_start)
            d = self.lmt_series_shaped_pulse_up.pulse_duration.get()
            # TODO: Track shaped-pulse metadata separately instead of
            # recording these as ordinary square pulses.
            self.register_pulse(duration_s=d, is_up=True)
            self.lmt_series_shaped_pulse_up.trigger_pulse()

        delay(30e-6)

    @kernel
    def shaped_lmt_series(self, offset_det, N_previous_pulses, N):

        # prepare the aoms
        self.lmt_series_shaped_pulse_up.prepare_pulse(
            frequency=CLOCK_UP_BEAM_INFO.frequency
        )
        self.lmt_series_shaped_pulse_down.prepare_pulse(
            frequency=CLOCK_DOWN_BEAM_INFO.frequency
        )
        delay_mu(int64(self.core.ref_multiplier))
        self.clock_down_dds.set_att(7.5)
        delay_mu(int64(self.core.ref_multiplier))
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
                + (i + N_previous_pulses) * (-1) ** (i) * momentum_kick
                + (-1) ** i * down_offset
            )

            # fire the pulse
            self.fire_shaped_lmt_pulse(f_i, pulse_type, t_start_lmt_pulse_mu)
            # disable ram mode
        self.lmt_series_shaped_pulse_up.disable_ram_mode()
        self.lmt_series_shaped_pulse_down.disable_ram_mode()
        # re-set the AOM to default
        # self.clock_default_setter._turn_on_ad9910s(light_enabled=False)
        self.clock_down_default_setter._turn_on_ad9910s(light_enabled=False)
        delay_mu(int64(self.core.ref_multiplier))
        self.clock_down_dds.set_att(0.0)

    @kernel
    def launch_hook_double_cloud(self):
        self.prepare_clock_delivery_aom()
        delay_mu(16)

        t_pi_down = self.down_pulses_duration.get()
        self.spectroscopy_pulse_time.get()

        lmt_detuning = self.lmt_launch_offset_detuning_double_cloud.get()
        self.lmt_launch_pulses_number.get()
        upper_selective_det = self.launch_upper_selective_cloud_detuning.get()
        self.launch_lower_selective_cloud_detuning.get()
        self.double_launch_last_pulse_detuning.get()

        self.stop_clock_opll_ramp()
        delay_mu(8)

        t_start_first_pulse_mu = now_mu() + self.core.seconds_to_mu(2e-6)
        self.set_clock_opll(
            start_opll_offset
            + self.calculate_frequency_for_first_pi_by_2_pulse(
                t_pulse_start_mu=t_start_first_pulse_mu,
                t_pi_pulse=t_pi_down,
            )
            + self.double_trap_launch_bs_detuning.get()
        )

        self.set_clock_down_dds(
            frequency=self.clock_switch_frequency_handle.get()
            + self.down_switch_detuning.get(),
            amplitude=self.clock_switch_amplitude_handle.get(),
        )

        # PI/2 PULSE DOWN BEAM
        at_mu(t_start_first_pulse_mu)
        d = t_pi_down
        self.register_pulse(duration_s=d, is_up=False)
        self.clock_down_dds.sw.on()
        delay(d)  # / 2)
        self.clock_down_dds.sw.off()

        # Shaped pulse with up beam, common to both clouds
        self.set_clock_up_dds(
            frequency=self.clock_switch_frequency_handle.get()
            + self.up_switch_detuning_higher_intensity.get(),
            amplitude=self.clock_switch_amplitude_handle.get(),
        )

        # prepare ram mode
        self.first_lmt_shaped_pulse.prepare_pulse(
            frequency=CLOCK_UP_BEAM_INFO.frequency
        )
        delay_mu(int64(self.core.ref_multiplier))
        self.clock_up_dds.set_att(0.0)
        delay_mu(int64(self.core.ref_multiplier))

        t_pulse = now_mu() + self.core.seconds_to_mu(1e-6)

        # set the frequency on the opll

        opll_frequency = (
            start_opll_offset
            + self.calculate_frequency_for_selective_lmt_pulse(
                t_pulse_start_mu=t_pulse, N_kicks=1
            )
            + upper_selective_det
        )

        at_mu(t_pulse)
        # ramp the offset upwards
        self.start_clock_opll_ramp(
            ramp_rate,
            opll_frequency,
            opll_frequency + 2e6,
            wave_type=1,
        )

        # pulse
        self.first_lmt_shaped_pulse.trigger_pulse()

        # stop the frequency ramp
        self.stop_clock_opll_ramp()

        # LMT series on the upper trap with shaped pulses

        # disable ram mode
        self.first_lmt_shaped_pulse.disable_ram_mode()
        # re-set the AOM to default
        self.clock_default_setter._turn_on_ad9910s(light_enabled=False)

        delay(1e-6)

        # LMT sequence on upper trap
        self.shaped_lmt_series(lmt_detuning, N_previous_pulses=3, N=1)

        # delay(self.delay_between_launches.get())

        # # LMT series on the lower trap
        # self.lmt_series_start_up(lmt_detuning, N_previous_pulses=0, N=N_launch + 1)

        # self.set_clock_up_dds(
        #     frequency=self.clock_switch_frequency_handle.get()
        #     + self.up_switch_detuning_lower_intensity.get(),
        #     amplitude=self.clock_switch_amplitude_handle.get(),
        # )

        # delay_mu(8)

        # # Clear out the ground state
        # self.fluorescence_pulse.do_imaging_pulse(
        #     duration=self.clearout_duration.get(),
        #     ignore_final_shutters=True,
        # )

        # # second before last pulse with a lower Rabi frequency, down beam pulse
        # self.do_selective_lmt_pulse_down_beam(
        #     lower_selective_det, N_kicks=int(N_launch), duration=95e-6
        # )

        # # last pulse, pi/2 with down beam and then throw away ground state
        # t_start_last_pulse_mu = now_mu() + self.core.seconds_to_mu(1e-6)
        # self.set_clock_opll(
        #     start_opll_offset
        #     - self.calculate_frequency_for_first_pi_by_2_pulse(
        #         t_pulse_start_mu=t_start_last_pulse_mu, t_pi_pulse=t_pi_down
        #     )
        #     + last_detuning
        #     - (N_launch + 1) * momentum_kick
        # )

        # at_mu(t_start_last_pulse_mu)
        # d = t_pi_up / 2
        # self.register_pulse(
        #     duration_s=d, is_up=True
        # )
        # self.clock_up_dds.sw.on()
        # delay(d)
        # self.clock_up_dds.sw.off()

        # delay(1e-6)

        # # Clear out the ground state
        # self.fluorescence_pulse.do_imaging_pulse(
        #     duration=200e-6,
        #     ignore_final_shutters=True,
        # )


class LMTInterferometryMixin(
    LMTBase, ClockInterferometryBase, DipoleTrapWithExperimentBase
):
    """
    Implements LMT interferometry after the launch

    Kernel hooks used (multiple mixins cannot use the same hooks):

    * :meth:`~do_experiment_after_dipole_trap`
    * :meth:`~post_sequence_cleanup_hook_lmt`
    """

    def build_fragment(self):
        super().build_fragment()

        self.setattr_param(
            "lmt_pulses_number",
            IntParam,
            "Number of pulses for LMT interferometry",
            default=41,
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
            default=0.2e3,
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
            default=-0.2e3,
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
            default=-1e3,
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
            default=100e-6,
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
        N_launch = 22
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
        last_bs_frequency = self.last_bs_freq.get()

        t_start_first_pulse_mu = now_mu() + self.core.seconds_to_mu(
            2e-6
        )  # Add a tiny delay to give us enough time to write to the DDS

        self.stop_clock_opll_ramp()
        delay_mu(8)

        self.set_clock_opll(
            start_opll_offset
            + self.calculate_frequency_for_first_pi_by_2_pulse(
                t_pulse_start_mu=t_start_first_pulse_mu,
                t_pi_pulse=t_pi_down,
            )
            + N_launch * 9.4e3
        )

        self.set_clock_down_dds(
            frequency=self.clock_switch_frequency_handle.get()
            + self.down_switch_detuning.get(),
            amplitude=self.clock_switch_amplitude_handle.get(),
            phase=self.calculate_phase_for_first_pi_by_2_pulse(),
        )

        # PI/2 PULSE DOWN BEAM
        at_mu(t_start_first_pulse_mu)
        d = t_pi_down / 2
        self.register_pulse(duration_s=d, is_up=False)
        self.clock_down_dds.sw.on()
        delay(d)
        self.clock_down_dds.sw.off()
        delay(100e-6)

        # First pulse with a lower Rabi frequency, up beam pulse
        if N > 1:
            self.set_clock_up_dds(
                frequency=self.clock_switch_frequency_handle.get()
                + self.up_switch_detuning_lower_intensity.get(),
                amplitude=self.clock_switch_amplitude_handle.get(),
                phase=self.calculate_phase_for_first_pi_by_2_pulse(),
            )

            delay_mu(8)
            self.do_selective_lmt_pulse(
                first_freq, N_kicks=2 + N_launch, att=10.5, duration=t_first_pi
            )

            # Clear out the ground state
            self.fluorescence_pulse.do_clearout_pulse(
                duration=self.clearout_duration.get(),
                ignore_final_shutters=True,
            )
            delay(8e-9)

            self.set_clock_up_dds(
                frequency=self.clock_switch_frequency_handle.get()
                + self.up_switch_detuning_higher_intensity.get(),
                amplitude=self.clock_switch_amplitude_handle.get(),
                phase=self.calculate_phase_for_first_pi_by_2_pulse(),
            )

        # LMT sequence on upper arm, starting on the excited state at n=2
        if N > 2:
            self.lmt_series(bs1_lmt_offset, N_previous_pulses=3 + N_launch, N=N - 2)

        delay_mu(8)
        t_end_bs_mu = now_mu()

        # Do a Stark shifting pulse in the first dark time
        self.stark_shifter.do_stark_pulse()

        # dark time
        t_start_lmt_mirror_mu = t_end_bs_mu + self.core.seconds_to_mu(
            self.delay_between_interferometry_pulses.get()
        )

        at_mu(t_start_lmt_mirror_mu)
        # LMT sequence on upper arm, momentum downwards
        if N > 2:

            self.lmt_series_start_down_launch_down(
                upper_mirror_offset, N_previous_pulses=N + N_launch, N=N - 2
            )
            delay_mu(8)

        if N > 1:

            # stark shift for low intensity up beam
            self.set_clock_up_dds(
                frequency=self.clock_switch_frequency_handle.get()
                + self.up_switch_detuning_lower_intensity.get(),
                amplitude=self.clock_switch_amplitude_handle.get(),
                phase=self.calculate_phase_for_first_pi_by_2_pulse(),
            )

            # Clear out the ground state
            self.fluorescence_pulse.do_clearout_pulse(
                duration=self.clearout_duration.get(),
                ignore_final_shutters=True,
            )
            delay(8e-9)

            # last pulse with a lower Rabi frequency, up beam pulse
            self.do_selective_lmt_pulse(
                last_upper_mirror_freq,
                N_kicks=2 + N_launch,
                att=10.5,
                duration=t_first_pi,
            )

        delay(8e-9)
        # Phase step
        self.set_clock_down_dds(
            frequency=self.clock_switch_frequency_handle.get()
            + self.down_switch_detuning.get(),
            amplitude=self.clock_switch_amplitude_handle.get(),
            phase=self.calculate_phase_for_pi_pulse(),
        )

        # delay to write onto the dds
        # delay(1e-6)

        # MIRROR PULSE DOWN BEAM
        t_start_mirror_pulse_mu = now_mu() + self.core.seconds_to_mu(
            50e-6
        )  # Add a tiny delay to give us enough time to write to the DDS

        self.set_clock_opll(
            start_opll_offset
            + self.calculate_frequency_for_pi_pulse(
                t_pulse_start_mu=t_start_mirror_pulse_mu,
                t_pi_pulse=t_pi_down,
            )
            + mirror_freq
            + N_launch * 9.4e3
        )
        at_mu(t_start_mirror_pulse_mu)
        d = t_pi_down
        self.register_pulse(duration_s=d, is_up=False)
        self.clock_down_dds.sw.on()
        delay(d)
        self.clock_down_dds.sw.off()

        delay(50e-6)

        if N > 1:
            # first lower arm mirror pulse with a lower Rabi frequency, up beam pulse
            self.do_selective_lmt_pulse(
                first_lower_mirror_freq,
                N_kicks=2 + N_launch,
                att=10.5,
                duration=t_first_pi,
            )

            # stark shift for high intensity up beam
            self.set_clock_up_dds(
                frequency=self.clock_switch_frequency_handle.get()
                + self.up_switch_detuning_higher_intensity.get(),
                amplitude=self.clock_switch_amplitude_handle.get(),
                phase=self.calculate_phase_for_first_pi_by_2_pulse(),
            )

            # Clear out the ground state
            self.fluorescence_pulse.do_clearout_pulse(
                duration=self.clearout_duration.get(),
                ignore_final_shutters=True,
            )
            delay(8e-9)

        if N > 2:
            # LMT series on lower arm, start from second pulse, down beam
            self.lmt_series(
                lower_mirror_offset, N_previous_pulses=3 + N_launch, N=N - 2
            )
            delay_mu(8)

        # Phase step
        delay(self.delay_between_interferometry_pulses.get())

        if N > 2:
            # LMT sequence on lower arm, momentum downwards
            self.lmt_series_start_down_launch_down(
                bs_detuning_lower, N_previous_pulses=N + N_launch, N=N - 2
            )

        if N > 1:

            # stark shift for low intensity up neam
            self.set_clock_up_dds(
                frequency=self.clock_switch_frequency_handle.get()
                + self.up_switch_detuning_lower_intensity.get(),
                amplitude=self.clock_switch_amplitude_handle.get(),
                phase=self.calculate_phase_for_first_pi_by_2_pulse(),
            )

            # Clear out the ground state
            self.fluorescence_pulse.do_clearout_pulse(
                duration=self.clearout_duration.get(),
                ignore_final_shutters=True,
            )
            delay(8e-9)

            # last lower arm bs pulse with a lower Rabi frequency, up beam pulse
            self.do_selective_lmt_pulse(
                last_selective_lower_bs_freq,
                N_kicks=2 + N_launch,
                att=10.5,
                duration=t_first_pi,
            )

            delay(8e-9)

        t_start_last_pulse_mu = now_mu() + self.core.seconds_to_mu(
            100e-6
        )  # Add a tiny delay to give us enough time to write to the DDS
        self.set_clock_opll(
            start_opll_offset
            + self.calculate_frequency_for_first_pi_by_2_pulse(
                t_pulse_start_mu=t_start_last_pulse_mu, t_pi_pulse=t_pi_down
            )
            + last_bs_frequency
            + N_launch * 9.4e3,
        )

        self.set_clock_down_dds(
            frequency=self.clock_switch_frequency_handle.get()
            + self.down_switch_detuning.get(),
            amplitude=self.clock_switch_amplitude_handle.get(),
            phase=self.calculate_phase_for_second_pi_by_2_pulse(),
        )

        # PI/2 PULSE

        at_mu(t_start_last_pulse_mu)
        delay_mu(8)
        self.start_clock_opll_ramp(
            ramp_rate,
            start_opll_offset
            + self.calculate_frequency_for_first_pi_by_2_pulse(
                t_pulse_start_mu=t_start_last_pulse_mu, t_pi_pulse=t_pi_down
            )
            + last_bs_frequency
            + N_launch * 9.4e3
            - 1e6,
            start_opll_offset
            + self.calculate_frequency_for_first_pi_by_2_pulse(
                t_pulse_start_mu=t_start_last_pulse_mu, t_pi_pulse=t_pi_down
            )
            + last_bs_frequency
            + N_launch * 9.4e3,
            wave_type=2,
        )
        delay_mu(8)
        d = t_pi_down / 2
        self.register_pulse(duration_s=d, is_up=False)
        self.clock_down_dds.sw.on()
        delay(d)
        self.clock_down_dds.sw.off()

        # # TRANSFER PULSES GROUND STATE
        # # stark shift for low intensity up neam
        # self.clock_up_dds.set(
        #     frequency=self.clock_switch_frequency_handle.get()
        #     + self.up_switch_detuning_lower_intensity.get(),
        #     amplitude=self.clock_switch_amplitude_handle.get(),
        #     phase=self.calculate_phase_for_first_pi_by_2_pulse(),
        # )

        # delay(8e-9)

        # # last lower arm bs pulse with a lower Rabi frequency, up beam pulse
        # self.do_selective_lmt_pulse(
        #     0.0,
        #     N_kicks=N_launch + 2,
        #     att=10.5,
        #     duration=t_first_pi,
        # )

        # delay(8e-9)

        # # Clear out the ground state
        # self.fluorescence_pulse.do_clearout_pulse(
        #     duration=self.clearout_duration.get(),
        #     ignore_final_shutters=True,
        # )
        # delay(8e-9)

        # # last lower arm bs pulse with a lower Rabi frequency, up beam pulse
        # self.do_selective_lmt_pulse(
        #     0.0,
        #     N_kicks=N_launch + 2,
        #     att=10.5,
        #     duration=t_first_pi,
        # )

        # delay(8e-9)

        t_start_last_ramp_mu = now_mu()
        self.start_clock_opll_ramp(
            ramp_rate,
            start_opll_offset
            + self.calculate_frequency_for_first_pi_by_2_pulse(
                t_pulse_start_mu=t_start_last_ramp_mu, t_pi_pulse=t_pi_down
            )
            # + last_bs_frequency
            + N_launch * 9.4e3 - 1e6,
            start_opll_offset
            + self.calculate_frequency_for_first_pi_by_2_pulse(
                t_pulse_start_mu=t_start_last_ramp_mu, t_pi_pulse=t_pi_down
            )
            # + last_bs_frequency
            + N_launch * 9.4e3,
            wave_type=2,
        )

    @kernel
    def post_sequence_cleanup_hook(self):
        self.post_sequence_cleanup_hook_base()
        self.post_sequence_cleanup_hook_lmt()

    @kernel
    def post_sequence_cleanup_hook_lmt(self):
        # stop the clock laser ramp
        self.stop_clock_opll_ramp()
        self.set_clock_opll(80e6)


class ShapedFirstPulseLMTInterferometryMixin(
    LMTInterferometryMixin, LMTLaunchDoubleTrapShapedPulseMixin
):
    """
    Implements LMT interferometry after the launch, starting with a shaped pulse addressing both clouds

    Kernel hooks used (multiple mixins cannot use the same hooks):
    """

    @kernel
    def do_clock_interferometry(self):
        self.prepare_clock_delivery_aom()
        delay_mu(16)

        N = self.lmt_pulses_number.get()
        t_pi_down = self.down_pulses_duration.get()
        self.first_lmt_duration.get()

        # frequencies
        first_freq = self.first_lmt_freq.get()
        bs1_lmt_offset = self.bs1_lmt_offset_detuning.get()
        upper_mirror_offset = self.upper_mirror_offset_detuning.get()
        self.last_upper_mirror_lmt_freq.get()
        mirror_freq = self.mirror_pulse_freq.get()
        self.first_lower_mirror_lmt_freq.get()
        self.lower_mirror_offset_detuning.get()
        self.lower_arm_bs_detuning.get()
        self.last_selective_lower_bs_freq.get()
        self.last_bs_freq.get()

        t_start_first_pulse_mu = now_mu() + self.core.seconds_to_mu(
            2e-6
        )  # Add a tiny delay to give us enough time to write to the DDS

        self.stop_clock_opll_ramp()
        delay_mu(8)

        self.set_clock_opll(
            start_opll_offset
            + self.calculate_frequency_for_first_pi_by_2_pulse(
                t_pulse_start_mu=t_start_first_pulse_mu,
                t_pi_pulse=t_pi_down,
            )
            + 10 * 9.4e3
        )

        self.set_clock_down_dds(
            frequency=self.clock_switch_frequency_handle.get()
            + self.down_switch_detuning.get(),
            amplitude=self.clock_switch_amplitude_handle.get(),
            phase=self.calculate_phase_for_first_pi_by_2_pulse(),
        )

        # PI/2 PULSE DOWN BEAM
        at_mu(t_start_first_pulse_mu)
        d = t_pi_down
        self.register_pulse(duration_s=d, is_up=False)
        self.clock_down_dds.sw.on()
        delay(d)  # / 2)
        self.clock_down_dds.sw.off()

        self.set_clock_up_dds(
            frequency=self.clock_switch_frequency_handle.get()
            + self.up_switch_detuning_lower_intensity.get(),
            amplitude=self.clock_switch_amplitude_handle.get(),
            phase=self.calculate_phase_for_first_pi_by_2_pulse(),
        )

        delay(1e-6)

        # First pulse with a lower Rabi frequency, up beam pulse
        if N > 1:
            self.first_shaped_lmt_pulse(first_freq, N_kicks=1 + 10)

            delay(8e-9)

        self.set_clock_up_dds(
            frequency=self.clock_switch_frequency_handle.get()
            + self.up_switch_detuning_higher_intensity.get(),
            amplitude=self.clock_switch_amplitude_handle.get(),
            phase=self.calculate_phase_for_first_pi_by_2_pulse(),
        )

        # LMT sequence on upper arm, starting on the excited state at n=2
        if N > 2:
            self.lmt_series(bs1_lmt_offset, N_previous_pulses=3 + 10, N=N - 2)

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
            upper_mirror_offset, N_previous_pulses=N + 10, N=N - 0
        )
        delay_mu(8)

        # stark shift for low intensity up beam
        self.set_clock_up_dds(
            frequency=self.clock_switch_frequency_handle.get()
            + self.up_switch_detuning_lower_intensity.get(),
            amplitude=self.clock_switch_amplitude_handle.get(),
            phase=self.calculate_phase_for_first_pi_by_2_pulse(),
        )

        # # pulse on lower arm, up beam
        # self.do_selective_lmt_pulse(
        #     last_upper_mirror_freq, N_kicks=-0 + 10, att=13.0, duration=t_first_pi
        # )

        delay(8e-9)
        # Phase step
        self.set_clock_down_dds(
            frequency=self.clock_switch_frequency_handle.get()
            + self.down_switch_detuning.get(),
            amplitude=self.clock_switch_amplitude_handle.get(),
            phase=self.calculate_phase_for_pi_pulse(),
        )

        # delay to write onto the dds
        # delay(1e-6)

        # MIRROR PULSE DOWN BEAM
        t_start_mirror_pulse_mu = now_mu() + self.core.seconds_to_mu(
            1e-6
        )  # Add a tiny delay to give us enough time to write to the DDS

        self.set_clock_opll(
            start_opll_offset
            + self.calculate_frequency_for_pi_pulse(
                t_pulse_start_mu=t_start_mirror_pulse_mu,
                t_pi_pulse=t_pi_down,
            )
            + mirror_freq
            + 8 * 9.4e3
        )
        at_mu(t_start_mirror_pulse_mu)
        d = t_pi_down
        self.register_pulse(duration_s=d, is_up=False)
        self.clock_down_dds.sw.on()
        delay(d)
        self.clock_down_dds.sw.off()

        delay(1e-6)

        # # first lower arm pulse - shaped, addressing both arms, up beam pulse
        # self.do_selective_lmt_pulse(
        #     first_lower_mirror_freq, N_kicks=0 + 10, att=13.0, duration=t_first_pi
        # )

        # # stark shift for high intensity up beam
        # self.set_clock_up_dds(
        #     frequency=self.clock_switch_frequency_handle.get()
        #     + self.up_switch_detuning_higher_intensity.get(),
        #     amplitude=self.clock_switch_amplitude_handle.get(),
        #     phase=self.calculate_phase_for_first_pi_by_2_pulse(),
        # )

        # # LMT series on lower arm, start from second pulse, down beam
        # self.lmt_series(lower_mirror_offset, N_previous_pulses=3 + 10, N=N - 2)
        # delay_mu(8)

        # # Phase step
        # delay(self.delay_between_interferometry_pulses.get())

        # # LMT sequence on lower arm, momentum downwards
        # self.lmt_series_start_down_launch_down(
        #     bs_detuning_lower, N_previous_pulses=N + 10, N=N - 2
        # )

        # # stark shift for low intensity up neam
        # self.set_clock_up_dds(
        #     frequency=self.clock_switch_frequency_handle.get()
        #     + self.up_switch_detuning_lower_intensity.get(),
        #     amplitude=self.clock_switch_amplitude_handle.get(),
        #     phase=self.calculate_phase_for_first_pi_by_2_pulse(),
        # )

        # # last lower arm bs pulse with a lower Rabi frequency, up beam pulse
        # self.do_selective_lmt_pulse(
        #     last_selective_lower_bs_freq, N_kicks=0 + 10, att=13.0, duration=t_first_pi
        # )

        # delay(8e-9)

        # t_start_last_pulse_mu = now_mu() + self.core.seconds_to_mu(
        #     2e-6
        # )  # Add a tiny delay to give us enough time to write to the DDS

        # self.set_clock_opll(
        #     start_opll_offset
        #     + self.calculate_frequency_for_first_pi_by_2_pulse(
        #         t_pulse_start_mu=t_start_last_pulse_mu, t_pi_pulse=t_pi_down
        #     )
        #     + last_bs_freq
        #     + 10 * 9.4e3
        # )
        # delay_mu(8)

        # self.set_clock_down_dds(
        #     frequency=self.clock_switch_frequency_handle.get()
        #     + self.down_switch_detuning.get(),
        #     amplitude=self.clock_switch_amplitude_handle.get(),
        #     phase=self.calculate_phase_for_second_pi_by_2_pulse(),
        # )

        # delay(1e-6)

        # # PI/2 PULSE

        # d = t_pi_down / 2
        # self.register_pulse(duration_s=d, is_up=False)
        # self.clock_down_dds.sw.on()
        # delay(d)
        # self.clock_down_dds.sw.off()
