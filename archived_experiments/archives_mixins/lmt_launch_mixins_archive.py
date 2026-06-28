import logging

from artiq.language import at_mu
from artiq.language import delay
from artiq.language import delay_mu
from artiq.language import kernel
from artiq.language import now_mu
from ndscan.experiment.parameters import FloatParam
from ndscan.experiment.parameters import FloatParamHandle
from numpy import int64
from pyaion.models import SUServoedBeam
from pyaion.models import UrukuledBeam

from repository.lib import constants
from repository.lib.experiment_templates.dipole_trap_experiment import (
    DipoleTrapWithExperimentBase,
)
from repository.lib.experiment_templates.mixins.LMT_launch_mixins import LMTLaunchMixin
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
            self.lmt_series_shaped_pulse_down.trigger_pulse()

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

        self.clock_opll.clock_frequency_ramper.stop_ramp()
        delay_mu(8)

        t_start_first_pulse_mu = now_mu() + self.core.seconds_to_mu(2e-6)
        self.clock_opll.clock_OPLL_offset.set(
            start_opll_offset
            + self.calculate_frequency_for_first_pi_by_2_pulse(
                t_pulse_start_mu=t_start_first_pulse_mu,
                t_pi_pulse=t_pi_down,
            )
            + self.double_trap_launch_bs_detuning.get()
        )

        self.clock_down_dds.set(
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
        self.clock_up_dds.set(
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
        self.clock_opll.clock_frequency_ramper.start_ramp(
            ramp_rate,
            opll_frequency,
            opll_frequency + 2e6,
            wave_type=1,
        )

        # pulse
        self.first_lmt_shaped_pulse.trigger_pulse()

        # stop the frequency ramp
        self.clock_opll.clock_frequency_ramper.stop_ramp()

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

        # self.clock_up_dds.set(
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
        # self.clock_opll.clock_OPLL_offset.set(
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
