import logging

from artiq.coredevice.core import Core
from artiq.language import kernel
from ndscan.experiment.parameters import FloatParam
from ndscan.experiment.parameters import FloatParamHandle
from numpy import int64
from pyaion.models import SUServoedBeam

from repository.lib import constants
from repository.lib.experiment_templates.mixins.clock_interferometry import (
    ClockInterferometryBase,
)
from repository.lib.experiment_templates.mixins.clock_shelving import (
    ClockShelvingAndClearoutBase,
)
from repository.lib.experiment_templates.mixins.clock_spectroscopy import (
    ClockRabiSpectroscopyBase,
)
from repository.lib.experiment_templates.mixins.LMT_launch_mixins import LMTBase

CLOCK_UP_BEAM_INFO = constants.URUKULED_BEAMS["clock_up"]
CLOCK_BEAM_DELIVERY_INFO: SUServoedBeam = constants.SUSERVOED_BEAMS["clock_delivery"]


logger = logging.getLogger(__name__)


class _DopplerCompensationBase(
    ClockShelvingAndClearoutBase,
):
    """
    Base for adding detunings to clock pulses to compensate for Doppler shifts
    accrued while the atoms fall.

    I.e. a poor-man's chirp.

    TODO: This uses the clock switch AOM instead of the SUServo AOM for
    convenience of coding. This would better be done with the SUServo AOM.
    """

    def build_fragment(self):
        super().build_fragment()

        self.core: Core

        self.setattr_param(
            "extra_clock_detuning",
            FloatParam,
            description="Extra clock detuning after Doppler correction",
            default=0.0,
            unit="kHz",
        )
        self.extra_clock_detuning: FloatParamHandle

        # Disable the detuning of the spectroscopy pulse via a parameter - we'll
        # handle it here instead
        if hasattr(self, "spectroscopy_pulse_aom_detuning"):
            self.override_param("spectroscopy_pulse_aom_detuning", 0.0)
        if hasattr(self, "shelving_pulse_aom_detuning"):
            self.override_param("shelving_pulse_aom_detuning", 0.0)

    @kernel
    def _calculate_chirp_required(self, t_drop: float):
        return t_drop * constants.GRAVITY_DOPPLER_PER_SEC_CLOCK


class DopplerCompensationForInterferometryMixin(
    _DopplerCompensationBase,
    ClockInterferometryBase,
):
    """
    Adds detunings to the interferometry pulses to compensate for Doppler shifts
    accrued while the atoms fall.

    I.e. a poor-man's chirp.

    TODO: This uses the clock switch AOM instead of the SUServo AOM for
    convenience of coding. This would better be done with the SUServo AOM.

    Kernel hooks used:

    * :meth:`~calculate_frequency_for_first_pi_by_2_pulse`
    * :meth:`~calculate_frequency_for_pi_pulse`
    * :meth:`~calculate_frequency_for_second_pi_by_2_pulse`
    """

    @kernel
    def calculate_frequency_for_first_pi_by_2_pulse(
        self, t_pulse_start_mu: int64, t_pi_pulse: float
    ) -> float:
        t_drop = (
            self.core.mu_to_seconds(
                t_pulse_start_mu - self.t_velocity_slicing_pulse_centre_mu
            )
            + t_pi_pulse / 2
        )
        return (
            self.clock_switch_frequency_handle.get()
            + self.extra_clock_detuning.get()
            + self._calculate_chirp_required(t_drop)
        )

    @kernel
    def calculate_frequency_for_pi_pulse(
        self, t_pulse_start_mu: int64, t_pi_pulse: float
    ) -> float:
        t_drop = (
            self.core.mu_to_seconds(
                t_pulse_start_mu - self.t_velocity_slicing_pulse_centre_mu
            )
            + t_pi_pulse
        )
        return (
            self.clock_switch_frequency_handle.get()
            + self.extra_clock_detuning.get()
            + self._calculate_chirp_required(t_drop)
        )

    @kernel
    def calculate_frequency_for_second_pi_by_2_pulse(
        self, t_pulse_start_mu: int64, t_pi_pulse: float
    ) -> float:
        t_drop = (
            self.core.mu_to_seconds(
                t_pulse_start_mu - self.t_velocity_slicing_pulse_centre_mu
            )
            + t_pi_pulse / 2
        )
        return (
            self.clock_switch_frequency_handle.get()
            + self.extra_clock_detuning.get()
            + self._calculate_chirp_required(t_drop)
        )


class DopplerCompensationForClockSpecMixin(
    _DopplerCompensationBase,
    ClockRabiSpectroscopyBase,
):
    """
    Adds detunings to the spectroscopy pulses to compensate for Doppler shifts
    accrued while the atoms fall.

    I.e. a poor-man's chirp.

    TODO: This uses the clock switch AOM instead of the SUServo AOM for
    convenience of coding. This would better be done with the SUServo AOM.

    Kernel hooks used:

    * :meth:`~calculate_frequency_for_first_pi_by_2_pulse`
    * :meth:`~calculate_frequency_for_pi_pulse`
    * :meth:`~calculate_frequency_for_second_pi_by_2_pulse`
    """

    @kernel
    def calculate_clock_delivery_freq(
        self, t_pulse_start_mu: int64, t_pi_pulse: float
    ) -> float:

        t_drop = self.core.mu_to_seconds(
            t_pulse_start_mu - self.t_velocity_slicing_pulse_centre_mu
        ) + (t_pi_pulse / 2)
        total_detuning = (
            self.extra_clock_detuning.get() + self._calculate_chirp_required(t_drop)
        )

        return self.clock_delivery_handles.frequency_handle.get() + total_detuning


class DopplerCompensationForLMTMixin(ClockShelvingAndClearoutBase, LMTBase):
    """
    Adds detunings to the LMT pulses to compensate for Doppler shifts
    accrued while the atoms fall.

    Kernel hooks used:

    * :meth:`~calculate_frequency_for_first_pi_by_2_pulse`
    """

    @kernel
    def calculate_frequency_for_first_pi_by_2_pulse(
        self, t_pulse_start_mu: int64, t_pi_pulse: float
    ) -> float:
        t_drop = self.core.mu_to_seconds(
            t_pulse_start_mu
            - self.t_velocity_slicing_pulse_centre_mu
            + self.core.seconds_to_mu(self.shelving_pulse_time.get() / 2)
        )
        print("freq calculated")

        return -self._calculate_chirp_required(t_drop) + self.momentum_kick.get()

    @kernel
    def calculate_frequency_for_second_lmt_pulse(
        self,
        t_pulse_start_mu: int64,
    ) -> float:
        t_drop = self.core.mu_to_seconds(
            t_pulse_start_mu
            - self.t_velocity_slicing_pulse_centre_mu
            + self.core.seconds_to_mu(self.shelving_pulse_time.get() / 2)
        )

        return -self._calculate_chirp_required(t_drop) + 3 * self.momentum_kick.get()

    @kernel
    def calculate_frequency_for_selective_lmt_pulse(
        self, t_pulse_start_mu: int64, N_kicks: int64
    ) -> float:
        t_drop = self.core.mu_to_seconds(
            t_pulse_start_mu
            - self.t_velocity_slicing_pulse_centre_mu
            + self.core.seconds_to_mu(self.shelving_pulse_time.get() / 2)
        )

        return (
            self._calculate_chirp_required(t_drop) - N_kicks * self.momentum_kick.get()
        )

    @kernel
    def calculate_frequency_for_pi_pulse(
        self, t_pulse_start_mu: int64, t_pi_pulse: float
    ) -> float:
        t_drop = self.core.mu_to_seconds(
            t_pulse_start_mu
            - self.t_velocity_slicing_pulse_centre_mu
            + self.core.seconds_to_mu(self.shelving_pulse_time.get() / 2)
        )

        return -self._calculate_chirp_required(t_drop) + self.momentum_kick.get()

    @kernel
    def _calculate_chirp_required(self, t_drop: float):
        return t_drop * constants.GRAVITY_DOPPLER_PER_SEC_CLOCK

    @kernel
    def get_t_start_shelving(self) -> int64:
        # return self.t_dipole_beams_off
        return self.t_velocity_slicing_pulse_centre_mu - self.core.seconds_to_mu(
            self.shelving_pulse_time.get() / 2
        )
