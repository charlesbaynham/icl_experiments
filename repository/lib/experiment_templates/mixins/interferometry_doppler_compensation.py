import logging

from artiq.language import kernel
from numpy import int64

# from pyaion.models import SUServoedBeam
from pyaion.models import SUServoedBeam

from repository.lib import constants
from repository.lib.experiment_templates.mixins.clock_interferometry import (
    ClockInterferometryBase,
)

CLOCK_BEAM_INFO = constants.URUKULED_BEAMS["clock_up"]
CLOCK_BEAM_DELIVERY_INFO: SUServoedBeam = constants.SUSERVOED_BEAMS["clock_delivery"]


logger = logging.getLogger(__name__)


class DopplerCompensationForInterferometryMixin(
    ClockInterferometryBase,
):
    """
    Adds detunings to the interferometry pulses to compensate for Doppler shifts accrued while the atoms fall.

    I.e. a poor-man's chirp.

    Kernel hooks used:

    * :meth:`~calculate_frequency_for_first_pi_by_2_pulse`
    * :meth:`~calculate_frequency_for_pi_pulse`
    * :meth:`~calculate_frequency_for_second_pi_by_2_pulse`
    """

    @kernel
    def calculate_frequency_for_first_pi_by_2_pulse(
        self, t_pulse_start_mu: int64, t_pi_pulse: float
    ) -> float:
        return self.clock_switch_frequency_handle.get()

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
