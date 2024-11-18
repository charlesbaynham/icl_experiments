import logging

from artiq.experiment import kernel
from ndscan.experiment.parameters import FloatParam
from ndscan.experiment.parameters import FloatParamHandle
from pyaion.models import SUServoedBeam
from pyaion.models import UrukuledBeam

from repository.lib import constants
from repository.lib.experiment_templates.mixins.clock_interferometry import (
    ClockInterferometryBase,
)

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

    @kernel
    def calculate_phase_for_first_pi_by_2_pulse(self) -> float:
        return self.phase_constant  # FIXME

    @kernel
    def calculate_phase_for_pi_pulse(self) -> float:
        return self.phase_constant + 1.0 * self.phase_step.get()  # FIXME

    @kernel
    def calculate_phase_for_second_pi_by_2_pulse(self) -> float:
        return self.phase_constant + 4.0 * self.phase_step.get()  # FIXME
