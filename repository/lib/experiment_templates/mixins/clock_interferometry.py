import logging

from artiq.coredevice.ad9910 import AD9910
from artiq.coredevice.suservo import Channel as SUServoChannel
from artiq.experiment import at_mu
from artiq.experiment import delay
from artiq.experiment import kernel
from artiq.experiment import now_mu
from ndscan.experiment import OnlineFit
from ndscan.experiment.entry_point import make_fragment_scan_exp
from ndscan.experiment.parameters import FloatParam
from ndscan.experiment.parameters import FloatParamHandle
from pyaion.fragments.default_beam_setter import make_set_beams_to_default
from pyaion.fragments.default_beam_setter import SetBeamsToDefaults
from pyaion.models import SUServoedBeam
from pyaion.models import UrukuledBeam

from repository.lib import constants

CLOCK_BEAM_INFO = constants.URUKULED_BEAMS["clock_up"]
CLOCK_BEAM_DELIVERY_INFO: SUServoedBeam = constants.SUSERVOED_BEAMS["clock_delivery"]

logger = logging.getLogger(__name__)

from repository.lib.experiment_templates.mixins.clock_spectroscopy import (
    ClockSpectroscopyMixin,
)


class ClockInterferometryMixin(ClockSpectroscopyMixin):
    def build_fragment(self):
        super().build_fragment()

        self.setattr_param(
            "delay_between_interferometry_pulses",
            FloatParam,
            "Delay between interferometry pulses",
            default=10e-6,
            unit="us",
        )
        self.delay_between_interferometry_pulses: FloatParamHandle

        self.setattr_param(
            "phase_step",
            FloatParam,
            "Phase step in interferometry sequence",
            default=0.0,
        )
        self.phase_step: FloatParamHandle

        # Allow negative phases up to -10
        self.phase_constant = 10.0

    def get_default_analyses(self):
        super_analysis = super().get_default_analyses()

        return super_analysis + [
            OnlineFit(
                "sinusoid",
                data={
                    "x": self.phase_step,
                    "y": self.excitation_fraction,
                },
                constants={
                    "t_dead": -100.0,
                },
            )
        ]

    @kernel
    def do_spectroscopy_hook(self):
        t_pi_pulse = self.spectroscopy_pulse_time.get()

        # Set frequency on the suservo, phase on the clock switch
        self.clock_delivery_setter.set_suservo(
            freq=CLOCK_BEAM_DELIVERY_INFO.frequency
            + self.spectroscopy_pulse_aom_detuning.get(),
            amplitude=CLOCK_BEAM_DELIVERY_INFO.initial_amplitude,
            attenuation=CLOCK_BEAM_DELIVERY_INFO.attenuation,
            rf_switch_state=True,
            setpoint_v=self.spectroscopy_clock_delivery_setpoint.get(),
            enable_iir=True,
        )
        self.clock_dds.set(
            frequency=CLOCK_BEAM_INFO.frequency,
            phase=self.phase_constant,
        )

        # PI/2 PULSE
        self.clock_dds.sw.on()
        delay(t_pi_pulse / 2)
        self.clock_dds.sw.off()
        t_end_pi_by_2_mu = now_mu()

        # Phase step
        self.clock_dds.set(
            frequency=CLOCK_BEAM_INFO.frequency,
            phase=self.phase_constant + 1.0 * self.phase_step.get(),
        )

        # PI PULSE
        at_mu(
            t_end_pi_by_2_mu
            + self.core.seconds_to_mu(self.delay_between_interferometry_pulses.get())
        )
        self.clock_dds.sw.on()
        delay(t_pi_pulse)
        self.clock_dds.sw.off()

        # Phase step
        t_end_pi_mu = now_mu()
        self.clock_dds.set(
            frequency=CLOCK_BEAM_INFO.frequency,
            phase=self.phase_constant + 4.0 * self.phase_step.get(),
        )

        # PI/2 PULSE
        at_mu(
            t_end_pi_mu
            + self.core.seconds_to_mu(self.delay_between_interferometry_pulses.get())
        )
        self.clock_dds.sw.on()
        delay(t_pi_pulse)
        self.clock_dds.sw.off()
