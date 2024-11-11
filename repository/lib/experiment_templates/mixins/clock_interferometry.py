import logging

from artiq.coredevice.suservo import SUServo
from artiq.experiment import at_mu
from artiq.experiment import delay
from artiq.experiment import kernel
from artiq.experiment import now_mu
from ndscan.experiment.parameters import FloatParam
from ndscan.experiment.parameters import FloatParamHandle
from pyaion.models import SUServoedBeam

from repository.lib import constants
from repository.lib.experiment_templates.dipole_trap_experiment import (
    DipoleTrapWithExperiment,
)
from repository.lib.experiment_templates.mixins.clock_spectroscopy import (
    ClockSpectroscopyBase,
)

CLOCK_BEAM_INFO = constants.URUKULED_BEAMS["clock_up"]
CLOCK_BEAM_DELIVERY_INFO: SUServoedBeam = constants.SUSERVOED_BEAMS["clock_delivery"]

logger = logging.getLogger(__name__)


class ClockInterferometryBase(ClockSpectroscopyBase):
    """
    Customizes ClockSpectroscopyBase for pi/2 - pi - pi/2 clock interferometry

    Kernel hooks used (not including wherever the interferometry is done - needs customization):

    * :meth:`~before_start_hook`
    * :meth:`~do_first_pulse`
    """

    def build_fragment(self):
        super().build_fragment()

        self.setattr_param(
            "spectroscopy_pulse_time",
            FloatParam,
            "Length of spectroscopy pulse",
            default=50e-6,
            unit="us",
        )
        self.spectroscopy_pulse_time: FloatParamHandle

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

    @kernel
    def do_clock_interferometry(self):
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
        delay(t_pi_pulse / 2)
        self.clock_dds.sw.off()


class ClockInterferometryWithSUServoMixin(ClockInterferometryBase):
    """
    Implements clock interferometry with the delivery SUServo instead of the
    clock switch AOM

    Kernel hooks:

    * :meth:`~before_start_hook`
    * :meth:`~do_first_pulse`
    """

    def host_setup(self):
        super().host_setup()

        self.clock_delivery_suservo = self.clock_delivery_setter.suservo_channel
        self.kernel_invariants.add("clock_suservo_channel")

        self.suservo_core: SUServo = self.clock_delivery_suservo.servo
        self.kernel_invariants.add("suservo_core")

    @kernel
    def before_start_hook(self):
        self.before_start_hook
        self.before_start_hook_clockspec()
        self.before_start_hook_clockinterferometry()

    @kernel
    def before_start_hook_clockinterferometry(self):
        # before_start_hook_clockspec has already set up the SUServo delivery
        # AOM with the right settings, but we'll overwrite all these except the
        # attenuator. Here, we make SUServo profiles manually with different
        # phases.

        offset = self.clock_delivery_setter.setpoint_to_offset(
            self.spectroscopy_clock_delivery_setpoint.get()
        )

        self.clock_delivery_suservo.set_dds(
            profile=0,
            frequency=CLOCK_BEAM_DELIVERY_INFO.frequency
            + self.spectroscopy_pulse_aom_detuning.get(),
            offset=offset,
            phase=self.phase_constant,
        )
        self.clock_delivery_suservo.set_dds(
            profile=1,
            frequency=CLOCK_BEAM_DELIVERY_INFO.frequency
            + self.spectroscopy_pulse_aom_detuning.get(),
            offset=offset,
            phase=self.phase_constant + 1.0 * self.phase_step.get(),
        )
        self.clock_delivery_suservo.set_dds(
            profile=2,
            frequency=CLOCK_BEAM_DELIVERY_INFO.frequency
            + self.spectroscopy_pulse_aom_detuning.get(),
            offset=offset,
            phase=self.phase_constant + 4.0 * self.phase_step.get(),
        )

        # Shut down the SUServo while we set up the profiles
        self.suservo_core.set_config(enable=0)

        # Configure default initial amplitudes and IIR settings for each
        # profile
        for i in range(3):
            self.clock_delivery_suservo.set_iir(
                profile=i,
                adc=self.clock_delivery_setter.sampler_channel,
                kp=0.0,
                ki=-10000.0,
                gain_limit=0.0,
                delay=0.0,
            )

        # Turn the core back on
        self.suservo_core.set_config(enable=1)

        # Start on profile 0 with the AOM on
        self.clock_delivery_suservo.set(en_out=1, en_iir=1, profile=0)

    @kernel
    def do_clock_interferometry(self):
        """
        Override the default interferometry (using the clock switch AOM) to use
        the SUServo for both phase and frequency instead. We reset the clock
        switch AOM to its default phase and frequency.
        """
        t_pi_pulse = self.spectroscopy_pulse_time.get()

        # Ensure the clock switch AOM is at its nominal frequency and phase
        self.clock_dds.set(
            frequency=CLOCK_BEAM_INFO.frequency,
            phase=0.0,
        )

        # Read out the current in-loop suservo control signal to avoid bumps
        # when we switch profile. This consumes all the slack
        settled_y_mu = self.clock_delivery_suservo.get_y_mu()

        # Write this value into all the profiles. We must add some slack first
        delay(1e-6)

        self.suservo_core.set_config(enable=0)
        for i in range(3):
            self.clock_delivery_suservo.set_y_mu(
                profile=i,
                y=settled_y_mu,
            )
        self.suservo_core.set_config(enable=1)

        # Switching profiles should now be bumpless.

        # Start with profile 0 for no phase shift
        self.clock_delivery_suservo.set(en_out=1, en_iir=1, profile=0)
        delay(2 * 1.2e-6)  # Add 2x servo cycles for the changes to filter through

        # PI/2 PULSE
        self.clock_dds.sw.on()
        delay(t_pi_pulse / 2)
        self.clock_dds.sw.off()
        t_end_pi_by_2_mu = now_mu()

        # Phase step
        self.clock_delivery_suservo.set(en_out=1, en_iir=1, profile=1)

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
        self.clock_delivery_suservo.set(en_out=1, en_iir=1, profile=2)

        # PI/2 PULSE
        at_mu(
            t_end_pi_mu
            + self.core.seconds_to_mu(self.delay_between_interferometry_pulses.get())
        )
        self.clock_dds.sw.on()
        delay(t_pi_pulse / 2)
        self.clock_dds.sw.off()


class ClockInterferometryRedMOTMixin(ClockInterferometryBase):
    """
    Implements clock interferometry after the red MOT

    Kernel hooks used (multiple mixins cannot use the same hooks):

    * :meth:`~before_start_hook`
    * :meth:`~do_experiment_after_red_mot_hook`
    * :meth:`~do_first_pulse`
    """

    @kernel
    def do_experiment_after_red_mot_hook(self):
        self.do_clock_interferometry()


class ClockInterferometryDipoleTrapMixin(
    ClockInterferometryBase, DipoleTrapWithExperiment
):
    """
    Implements clock interferometry after the dipole trap

    Kernel hooks used (multiple mixins cannot use the same hooks):

    * :meth:`~before_start_hook`
    * :meth:`~do_experiment_after_dipole_trap_hook`
    * :meth:`~do_first_pulse`
    """

    @kernel
    def do_experiment_after_dipole_trap_hook(self):
        self.do_clock_interferometry()
