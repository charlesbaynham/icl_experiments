import logging

from artiq.language import kernel
from ndscan.experiment import Fragment
from ndscan.experiment.parameters import FloatParam
from ndscan.experiment.parameters import FloatParamHandle
from ndscan.experiment.parameters import IntParam
from ndscan.experiment.parameters import IntParamHandle
from ndscan.experiment.result_channels import FloatChannel

from repository.lib.experiment_templates.dipole_trap_experiment import (
    DipoleTrapWithExperiment,
)
from repository.lib.experiment_templates.mixins.clock_interferometry import (
    ClockInterferometryBase,
)
from repository.lib.utils import GaussianRandom

logger = logging.getLogger(__name__)


class _ClockInterferometryWithNoise(ClockInterferometryBase):
    """
    Customizes ClockInterferometryBase for pi/2 - pi - pi/2 clock interferometry
    with noise added as a random phase step between pulses 1/2 and 2/3

    Kernel hooks used (not including wherever the interferometry is done - needs
    customization):

    * :meth:`~before_start_hook`
    * :meth:`~do_first_pulse`
    """

    def build_fragment(self):
        super().build_fragment()

        class GaussianNoisePhase(Fragment):
            """
            Using a random noise generator over the 0,1 interval, draw two
            samples from two Gaussians with the given mean and variance

            This is implemented as a Fragment so we can use device_setup (which
            we can't do from a mixin).
            """

            def build_fragment(self):
                self.setattr_param(
                    "random_seed",
                    IntParam,
                    description="Seed for pseudo-random number generator",
                    default=12345,
                )
                self.random_seed: IntParamHandle

                self.setattr_param(
                    "phase_step_one_std",
                    FloatParam,
                    description="Std. dev. of phase step 1 in turns",
                    default=0.0,
                )
                self.phase_step_one_std: FloatParamHandle

                self.setattr_param(
                    "phase_step_one_mean",
                    FloatParam,
                    description="Mean of phase step 1 in turns",
                    default=0.0,
                )
                self.phase_step_one_mean: FloatParamHandle

                self.setattr_param(
                    "phase_step_two_std",
                    FloatParam,
                    description="Std. dev. of phase step 2 in turns",
                    default=0.0,
                )
                self.phase_step_two_std: FloatParamHandle

                self.setattr_param(
                    "phase_step_two_mean",
                    FloatParam,
                    description="Mean of phase step 2 in turns",
                    default=0.0,
                )
                self.phase_step_two_mean: FloatParamHandle

            def host_setup(self):
                # Make a random noise generator
                self.rng = GaussianRandom(self, seed=self.random_seed.get())

                self.random_phase_one = 0.0
                self.random_phase_two = 0.0

                super().host_setup()

            @kernel
            def device_setup(self):
                self.device_setup_subfragments()

                self.random_phase_one = (
                    self.phase_step_one_std.get() * self.rng.next()
                    + self.phase_step_one_mean.get()
                )
                self.random_phase_two = (
                    self.phase_step_two_std.get() * self.rng.next()
                    + self.phase_step_two_mean.get()
                )

            @kernel
            def get_random_phases(self) -> tuple[float, float]:
                return self.random_phase_one, self.random_phase_two

        self.setattr_fragment("phase_rng", GaussianNoisePhase)
        self.phase_rng: GaussianNoisePhase

        # Expose params here
        self.setattr_param_rebind("phase_step_one_mean", self.phase_rng)
        self.setattr_param_rebind("phase_step_two_mean", self.phase_rng)

        # For now, bind the std. dev. of the phase steps together
        self.setattr_param_like(
            "phase_step_std",
            self.phase_rng,
            original_name="phase_step_one_std",
            description="Std. dev. of both phase steps in turns",
        )
        self.phase_rng.bind_param("phase_step_one_std", self.phase_step_std)
        self.phase_rng.bind_param("phase_step_two_std", self.phase_step_std)
        # self.setattr_param_rebind("phase_step_one_std", self.phase_rng)
        # self.setattr_param_rebind("phase_step_two_std", self.phase_rng)

        # Make output channels to record the phases we generate for convenience
        # (we could regenerate them from the seed but this is easier)
        self.setattr_result(
            "random_phase_one", FloatChannel, display_hints={"priority": -1}
        )
        self.random_phase_one: FloatChannel

        self.setattr_result(
            "random_phase_two", FloatChannel, display_hints={"priority": -1}
        )
        self.random_phase_two: FloatChannel

    @kernel
    def calculate_phase_for_first_pi_by_2_pulse(self) -> float:
        return self.phase_constant  # Unchanged from base

    @kernel
    def calculate_phase_for_pi_pulse(self) -> float:
        random_phase_one = self.phase_rng.get_random_phases()[0]
        self.random_phase_one.push(random_phase_one)
        return self.phase_constant + 1.0 * self.phase_step.get() + random_phase_one

    @kernel
    def calculate_phase_for_second_pi_by_2_pulse(self) -> float:
        random_phase_two = self.phase_rng.get_random_phases()[1]
        self.random_phase_two.push(random_phase_two)
        return self.phase_constant + 4.0 * self.phase_step.get() + random_phase_two


class ClockInterferometryWithNoiseDipoleTrapMixin(
    _ClockInterferometryWithNoise, DipoleTrapWithExperiment
):
    """
    Implements clock interferometry after the dipole trap with added noisy phase steps between pulses

    Kernel hooks used (multiple mixins cannot use the same hooks):

    * :meth:`~before_start_hook`
    * :meth:`~do_experiment_after_dipole_trap_hook`
    * :meth:`~do_first_pulse`
    """

    @kernel
    def do_experiment_after_dipole_trap_hook(self):
        self.do_clock_interferometry()
