"""
Define the phases available for making red MOTs

This module currently breaks the rule about only storing physics-determined
numbers in `constants.py`.
"""

import repository.lib.constants as constants
from repository.lib.fragments.ramping_phase_bound import (
    GeneralRampingPhaseWithBindingAndMOTField,
)


class RedRampingPhaseWithFieldsAndSUServoBindings(
    GeneralRampingPhaseWithBindingAndMOTField
):
    """
    Subclass the GeneralRampingPhase specifically for red MOTs. I.e.:

    * Specify the 689 double-passed AOM as an Urukul to ramp
    * Control the 4 red beams
    * Add control of the B fields in chamber 2
    """

    urukuls = ["urukul9910_aom_doublepass_689_red_injection"]
    default_urukul_amplitudes_start = [1.0]
    default_urukul_amplitudes_end = [1.0]
    suservos = [
        "suservo_aom_singlepass_689_red_mot_sigmaplus",
        "suservo_aom_singlepass_689_red_mot_sigmaminus",
        "suservo_aom_singlepass_689_red_mot_diagonal",
        "suservo_aom_singlepass_689_up",
    ]

    # These must be overridden / rebound by consumer fragments otherwise not
    # much will happen. This is done so that all the phases can share the same
    # detuning / nominal setpoints. Use
    # self.bind_suservo_setpoint_params_to_default_beam_setter for this.
    default_urukul_nominal_frequencies = [0.0]
    default_suservo_nominal_setpoints = [0.0] * 4


class BroadbandRedPhase(RedRampingPhaseWithFieldsAndSUServoBindings):
    """
    Note that this phase does not start / stop the modulation of the IJD AOM.
    You must do this elsewhere
    """

    duration_default = constants.RED_BROADBAND_DURATION
    time_step_default = constants.RED_BROADBAND_TIMESTEP

    # For the broadband stage we don't want control over the Urukul since the
    # frequency is controlled by the fast ramp rate. The parameters controlling
    # that ramp rate are not currently rampable - we could add this if required
    # but it's getting conceptually complicated
    urukuls = []
    default_urukul_amplitudes_start = []
    default_urukul_amplitudes_end = []
    default_urukul_detunings_start = []
    default_urukul_detunings_end = []
    default_urukul_nominal_frequencies = []

    default_suservo_setpoint_multiples_start = (
        constants.RED_BROADBAND_SUSERVO_MULTIPLES_START
    )
    default_suservo_setpoint_multiples_end = (
        constants.RED_BROADBAND_SUSERVO_MULTIPLES_END
    )
    general_setter_default_starts = constants.RED_BROADBAND_MOT_CURRENT_START
    general_setter_default_ends = constants.RED_BROADBAND_MOT_CURRENT_END


class NarrowRedCapturePhase(RedRampingPhaseWithFieldsAndSUServoBindings):
    duration_default = constants.RED_CAPTURE_DURATION
    default_urukul_detunings_start = constants.RED_CAPTURE_DETUNING_START
    default_urukul_detunings_end = constants.RED_CAPTURE_DETUNING_END
    default_suservo_setpoint_multiples_start = (
        constants.RED_CAPTURE_SUSERVO_MULTIPLES_START
    )
    default_suservo_setpoint_multiples_end = constants.RED_CAPTURE_SUSERVO_MULTIPLES_END
    general_setter_default_starts = constants.RED_CAPTURE_MOT_CURRENT_START
    general_setter_default_ends = constants.RED_CAPTURE_MOT_CURRENT_END


class NarrowRedCompressionPhase(RedRampingPhaseWithFieldsAndSUServoBindings):
    duration_default = constants.RED_COMPRESSION_DURATION
    default_suservo_setpoint_multiples_start = (
        constants.RED_COMPRESSION_SUSERVO_MULTIPLES_START
    )
    default_suservo_setpoint_multiples_end = (
        constants.RED_COMPRESSION_SUSERVO_MULTIPLES_END
    )
    default_urukul_detunings_start = constants.RED_COMPRESSION_DETUNING_START
    default_urukul_detunings_end = constants.RED_COMPRESSION_DETUNING_END
    general_setter_default_starts = constants.RED_COMPRESSION_MOT_CURRENT_START
    general_setter_default_ends = constants.RED_COMPRESSION_MOT_CURRENT_END
