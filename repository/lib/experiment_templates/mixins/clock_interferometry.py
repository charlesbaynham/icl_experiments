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

from repository.lib import constants
from repository.lib.experiment_templates.dipole_trap_experiment import (
    DipoleTrapWithExperimentBase,
)
from repository.lib.experiment_templates.mixins.clock_spectroscopy import (
    ClockSpectroscopyBase,
)
from repository.lib.fragments.stark_shifter import StarkShifter

CLOCK_UP_BEAM_INFO = constants.URUKULED_BEAMS["clock_up"]
CLOCK_BEAM_DELIVERY_INFO: SUServoedBeam = constants.SUSERVOED_BEAMS["clock_delivery"]


logger = logging.getLogger(__name__)


class ClockInterferometryBase(
    ClockSpectroscopyBase,
):
    """
    Customizes ClockSpectroscopyBase for pi/2 - pi - pi/2 clock interferometry

    Kernel hooks used (not including wherever the interferometry is done - needs customization):

    * :meth:`~before_start_hook`
    * :meth:`~do_first_pulse`

    Kernel hooks provided:

    * :meth:`~calculate_phase_for_first_pi_by_2_pulse`
    * :meth:`~calculate_phase_for_pi_pulse`
    * :meth:`~calculate_phase_for_second_pi_by_2_pulse`
    * :meth:`~calculate_frequency_for_first_pi_by_2_pulse`
    * :meth:`~calculate_frequency_for_pi_pulse`
    * :meth:`~calculate_frequency_for_second_pi_by_2_pulse`
    * :meth:`~do_clock_interferometry`
    """

    def build_fragment(self):
        super().build_fragment()

        self.setattr_param(
            "spectroscopy_pulse_time",
            FloatParam,
            "Length of spectroscopy pulse",
            default=constants.CLOCK_PI_TIME,
            unit="us",
        )
        self.spectroscopy_pulse_time: FloatParamHandle

        self.setattr_param(
            "delay_between_interferometry_pulses",
            FloatParam,
            "Delay between interferometry pulses",
            default=constants.DELAY_BETWEEN_INTERFEROMETRY_PULSES,
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

        # Add control of the Stark shifting 689 beam
        self.setattr_fragment("stark_shifter", StarkShifter)
        self.stark_shifter: StarkShifter
        self.setattr_param_rebind("stark_pulse_duration", self.stark_shifter)

        # Allow negative phases up to -10
        self.phase_constant = 10.0
        self.clock_up_dds_frequency_pi_pulse = 0.0
        self.clock_up_dds_frequency_final_pi_by_2_pulse = 0.0

    @kernel
    def calculate_frequency_for_first_pi_by_2_pulse(
        self, t_pulse_start_mu: int64, t_pi_pulse: float
    ) -> float:
        return 0.0

    @kernel
    def calculate_frequency_for_pi_pulse(
        self, t_pulse_start_mu: int64, t_pi_pulse: float
    ) -> float:
        return self.clock_switch_frequency_handle.get()

    @kernel
    def calculate_frequency_for_second_pi_by_2_pulse(
        self, t_pulse_start_mu: int64, t_pi_pulse: float
    ) -> float:
        return self.clock_switch_frequency_handle.get()

    @kernel
    def calculate_phase_for_first_pi_by_2_pulse(self) -> float:
        return self.phase_constant

    @kernel
    def calculate_phase_for_pi_pulse(self) -> float:
        return self.phase_constant + 1.0 * self.phase_step.get()

    @kernel
    def calculate_phase_for_second_pi_by_2_pulse(self) -> float:
        return self.phase_constant + 4.0 * self.phase_step.get()

    @kernel
    def start_interferometry_hook(self):
        pass

    @kernel
    def end_interferometry_hook(self):
        pass

    @kernel
    def do_clock_interferometry(self):
        self.start_interferometry_hook()

        t_pi_pulse = self.spectroscopy_pulse_time.get()

        self.prepare_clock_delivery_aom()

        t_start_first_pulse_mu = now_mu() + self.core.seconds_to_mu(
            1e-6
        )  # Add a tiny delay to give us enough time to write to the DDS
        self.clock_up_dds.set(
            frequency=self.calculate_frequency_for_first_pi_by_2_pulse(
                t_pulse_start_mu=t_start_first_pulse_mu, t_pi_pulse=t_pi_pulse
            ),
            amplitude=self.clock_switch_amplitude_handle.get(),
            phase=self.calculate_phase_for_first_pi_by_2_pulse(),
        )

        # PI/2 PULSE
        at_mu(t_start_first_pulse_mu)
        self.clock_up_dds.sw.on()
        delay(t_pi_pulse / 2)
        self.clock_up_dds.sw.off()
        t_end_pi_by_2_mu = now_mu()
        delay_mu(int64(self.core.ref_multiplier))

        # Do a Stark shifting pulse in the first dark time
        self.stark_shifter.do_stark_pulse()

        # Phase step
        t_start_pi_pulse_mu = t_end_pi_by_2_mu + self.core.seconds_to_mu(
            self.delay_between_interferometry_pulses.get()
        )

        self.clock_up_dds.set(
            frequency=self.calculate_frequency_for_pi_pulse(
                t_pulse_start_mu=t_start_pi_pulse_mu, t_pi_pulse=t_pi_pulse
            ),
            amplitude=self.clock_switch_amplitude_handle.get(),
            phase=self.calculate_phase_for_pi_pulse(),
        )

        # PI PULSE
        at_mu(t_start_pi_pulse_mu)
        self.clock_up_dds.sw.on()
        delay(t_pi_pulse)
        self.clock_up_dds.sw.off()

        # Phase step
        t_end_pi_mu = now_mu()
        t_start_final_pulse_mu = t_end_pi_mu + self.core.seconds_to_mu(
            self.delay_between_interferometry_pulses.get()
        )
        self.clock_up_dds.set(
            frequency=self.calculate_frequency_for_second_pi_by_2_pulse(
                t_pulse_start_mu=t_start_final_pulse_mu, t_pi_pulse=t_pi_pulse
            ),
            amplitude=self.clock_switch_amplitude_handle.get(),
            phase=self.calculate_phase_for_second_pi_by_2_pulse(),
        )

        # PI/2 PULSE
        at_mu(t_start_final_pulse_mu)
        self.clock_up_dds.sw.on()
        delay(t_pi_pulse / 2)
        self.clock_up_dds.sw.off()

        self.end_interferometry_hook()


class ClockInterferometryDipoleTrapMixin(
    ClockInterferometryBase, DipoleTrapWithExperimentBase
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
