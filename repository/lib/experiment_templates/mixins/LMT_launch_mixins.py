import logging

from artiq.coredevice.ad9910 import AD9910
from numpy import int64
from artiq.language import at_mu
from artiq.language import delay
from artiq.language import delay_mu
from artiq.language import kernel
from artiq.language import now_mu
from ndscan.experiment import Fragment
from ndscan.experiment.parameters import FloatParam
from ndscan.experiment.parameters import FloatParamHandle
from ndscan.experiment.parameters import IntParam
from ndscan.experiment.parameters import IntParamHandle
from pyaion.fragments.default_beam_setter import SetBeamsToDefaults
from pyaion.fragments.default_beam_setter import make_set_beams_to_default
from pyaion.fragments.suservo import LibSetSUServoStatic
from pyaion.models import SUServoedBeam
from pyaion.models import UrukuledBeam

from repository.lib import constants
from repository.lib.experiment_templates.dipole_trap_experiment import (
    DipoleTrapWithExperiment,
)
from repository.lib.experiment_templates.red_mot_experiment import RedMOTWithExperiment
from repository.lib.fragments.beams.glitchfree_urukul_default_attenuation import (
    GlitchFreeUrukulDefaultAttenuation,
)
from repository.lib.experiment_templates.mixins.clock_interferometry import (
    ClockInterferometryBase,
)
from repository.lib.experiment_templates.mixins.clock_spectroscopy import (
    ClockSpectroscopyBase,
)
from repository.lib.fragments.clock_opll_controller import ClockOPLLController

CLOCK_UP_BEAM_INFO: UrukuledBeam = constants.URUKULED_BEAMS["clock_up"]
CLOCK_DOWN_BEAM_INFO: UrukuledBeam = constants.URUKULED_BEAMS["clock_down"]
CLOCK_BEAM_DELIVERY_INFO: SUServoedBeam = constants.SUSERVOED_BEAMS["clock_delivery"]

ramp_rate = constants.GRAVITY_DOPPLER_PER_SEC_CLOCK
start_opll_offset = 80e6

logger = logging.getLogger(__name__)


class LMTBase(RedMOTWithExperiment, ClockSpectroscopyBase):
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

        self.setattr_param(
            "spectroscopy_pulse_time",
            FloatParam,
            "Duration of an up beam launch pulse",
            default=constants.CLOCK_PI_TIME,
            unit="us",
        )
        self.spectroscopy_pulse_time: FloatParamHandle

        self.setattr_param(
            "down_pulses_duration",
            FloatParam,
            "Duration of a down beam launch pulse",
            default=constants.DOWN_CLOCK_BEAM_PI_TIME,
            unit="us",
        )
        self.down_pulses_duration: FloatParamHandle

        if not hasattr(self, "clock_opll"):
            self.setattr_fragment("clock_opll", ClockOPLLController)
            self.clock_opll: ClockOPLLController


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
            "momentum_kick",
            FloatParam,
            "Momentum kick",
            default=constants.MOMENTUM_KICK_DETUNING,
            unit="kHz",
        )
        self.momentum_kick: FloatParamHandle

        self.setattr_param(
            "lmt_offset_detuning",
            FloatParam,
            "LMT offset detuning",
            default=constants.LMT_OFFSET_DETUNING,
            unit="kHz",
        )
        self.lmt_offset_detuning: FloatParamHandle

        self.setattr_param(
            "down_offset_detuning",
            FloatParam,
            "Extra detuning for up beam",
            default=constants.LMT_DOWN_BEAM_RECOIL_SHIFT,
            unit="kHz",
        )
        self.down_offset_detuning: FloatParamHandle

    @kernel
    def launch_hook(self):
        self.prepare_clock_delivery_aom()
        delay_mu(16)
        start_detuning = self.lmt_offset_detuning.get()
        lmt_number = self.lmt_launch_pulses_number.get()
        self.lmt_series(start_detuning, lmt_number)

    @kernel
    def lmt_series(self, offset_det, N):

        kick = self.momentum_kick.get()
        total_ramp_time = 0.0

        t_start_ramp = now_mu()
        for i in range(N):

            if i % 2 == 0:
                down_offset = 0.0
            else:
                down_offset = self.down_offset_detuning.get()

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
            if pulse_type == "up":
                self.fluorescence_pulse.do_imaging_pulse(
                    duration=self.clearout_duration.get(),
                    ignore_final_shutters=True,
                )
                delay(8e-9)

            t_end_pulse = now_mu()
            total_ramp_time = self.core.mu_to_seconds(t_end_pulse - t_start_ramp)

    @kernel
    def fire_lmt_pulse(self, start_freq, type):
        # stop the ramp
        self.clock_opll.clock_frequency_ramper.stop_ramp()
        # set the offset frequency
        self.clock_opll.clock_OPLL_offset.set(start_freq)
        delay(8e-9)

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


class LMTInterferometryMixin(
    LMTLaunchMixin, ClockInterferometryBase, DipoleTrapWithExperiment
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
            default=10,
        )
        self.lmt_pulses_number: IntParamHandle

        self.setattr_param(
            "bs1_lmt_offset_detuning",
            FloatParam,
            "LMT detuning after 1st BS",
            default=0.0,
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
            "lower_mirror_offset_detuning",
            FloatParam,
            "LMT detuning for lower arm mirror",
            default=0.0,
            unit="kHz",
        )
        self.lower_mirror_offset_detuning: FloatParamHandle

    @kernel
    def do_experiment_after_dipole_trap_hook(self):
        self.do_clock_interferometry()

    @kernel
    def do_clock_interferometry(self):

        N = self.lmt_pulses_number.get()
        bs1_lmt_offset = self.bs1_lmt_offset_detuning.get()
        t_pi_up = self.spectroscopy_pulse_time.get()

        self.prepare_clock_delivery_aom()

        t_start_first_pulse_mu = now_mu()
        # PI/2 PULSE UP BEAM
        at_mu(t_start_first_pulse_mu)
        self.clock_up_dds.sw.on()
        delay(t_pi_up / 2)
        self.clock_up_dds.sw.off()
        t_end_pi_by_2_mu = now_mu()
        delay_mu(25e-6)

        # LMT sequence on upper arm
        self.lmt_series(bs1_lmt_offset, (N - 1))

        # Phase step
        t_start_upper_mirror_mu = t_end_pi_by_2_mu + self.core.seconds_to_mu(
            self.delay_between_interferometry_pulses.get()
        )

        # Mirror pulse upper arm
        at_mu(t_start_upper_mirror_mu)
        self.lmt_series(self.upper_mirror_offset_detuning, N)

        # Mirror pulse lower arm
        self.lmt_series(self.lower_mirror_offset_detuning, N)

        # Phase step
        t_end_pi_mu = now_mu()
        t_start_final_bs_mu = t_end_pi_mu + self.core.seconds_to_mu(
            self.delay_between_interferometry_pulses.get()
        )

        # PI/2 PULSE
        at_mu(t_start_final_bs_mu)
        self.clock_up_dds.sw.on()
        delay(t_pi_up / 2)
        self.clock_up_dds.sw.off()

        # LMT sequence on lower arm
        self.lmt_series(bs1_lmt_offset, (N - 1))
