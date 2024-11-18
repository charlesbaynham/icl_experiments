import logging

from artiq.experiment import kernel
from ndscan.experiment import Fragment
from ndscan.experiment.parameters import FloatParam
from ndscan.experiment.parameters import (
    FloatParamHandle,
    IntParamHandle,
    IntParam,
)
from pyaion.models import SUServoedBeam
from pyaion.models import UrukuledBeam

from repository.lib import constants
from repository.lib.experiment_templates.mixins.clock_interferometry import (
    ClockInterferometryBase,
)
from repository.lib.utils import SimpleRandom

CLOCK_BEAM_INFO = constants.URUKULED_BEAMS["clock_up"]
CLOCK_BEAM_DELIVERY_INFO: SUServoedBeam = constants.SUSERVOED_BEAMS["clock_delivery"]

STARK_689_BEAM_INFO: UrukuledBeam = constants.URUKULED_BEAMS["stark_shifter_689"]

logger = logging.getLogger(__name__)


class ClockInterferometryWithNoise(ClockInterferometryBase):
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

        self.setattr_param(
            "phase_step_one_variance",
            FloatParam,
            description="Variance of phase step 1 in turns",
            default=0.0,
        )
        self.phase_step_one_variance: FloatParamHandle

        self.setattr_param(
            "phase_step_one_mean",
            FloatParam,
            description="Mean of phase step 1 in turns",
            default=0.0,
        )
        self.phase_step_one_mean: FloatParamHandle

        self.setattr_param(
            "phase_step_two_variance",
            FloatParam,
            description="Variance of phase step 2 in turns",
            default=0.0,
        )
        self.phase_step_two_variance: FloatParamHandle

        self.setattr_param(
            "phase_step_two_mean",
            FloatParam,
            description="Mean of phase step 2 in turns",
            default=0.0,
        )
        self.phase_step_two_mean: FloatParamHandle

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

            def host_setup(self):
                # Make a random noise generator
                self.rng = SimpleRandom(self, seed=self.random_seed.get())

                super().host_setup()

            @kernel
            def device_setup(self):
                self.device_setup_subfragments()

                self.random_phase = self.rng()

    @kernel
    def calculate_phase_for_first_pi_by_2_pulse(self) -> float:
        return self.phase_constant  # FIXME

    @kernel
    def calculate_phase_for_pi_pulse(self) -> float:
        return self.phase_constant + 1.0 * self.phase_step.get()  # FIXME

    @kernel
    def calculate_phase_for_second_pi_by_2_pulse(self) -> float:
        return self.phase_constant + 4.0 * self.phase_step.get()  # FIXME
