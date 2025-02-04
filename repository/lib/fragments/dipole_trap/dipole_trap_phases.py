"""
Define the phases available in the dipole trap.
"""

import repository.lib.constants as constants
from repository.lib.fragments.ramping_phase_bound import (
    GeneralRampingPhaseWithBindingAndBiasField,
)
from repository.lib.fragments.ramping_phase_bound import GeneralRampingPhaseWithBinding

suservos_molasses = [
    "suservo_aom_singlepass_689_red_mot_sigmaplus",
    "suservo_aom_singlepass_689_red_mot_sigmaminus",
    "suservo_aom_singlepass_689_red_mot_diagonal",
    "suservo_aom_singlepass_689_up",
]
urukuls_molasses = ["urukul9910_aom_doublepass_689_red_injection"]

suservos_optical_pumping = [
    "suservo_aom_singlepass_689_red_mot_sigmaplus",
    "suservo_aom_singlepass_689_red_mot_sigmaminus",
]
urukuls_optical_pumping = ["urukul9910_aom_doublepass_689_red_spinpol"]

suservos_XODT = [
    "suservo_aom_1064_delivery",
    "suservo_aom_down_813",
]
suservos_cavity_lattice = [
    "suservo_aom_singlepass_1379_cavity_input",
]


class MolassesInXODT(GeneralRampingPhaseWithBindingAndBiasField):
    """
    A molasses phase with ramps for 689 nm molasses beams, a 1064/813 nm XODT, and bias fields

    We only define a single set of ramp parameters (unlike in the red MOT ramping phases) because we will probably only use this phase on Sr87

    The default suservo and urukul frequency "nominals" are set to zero at this point: To use these beams, they must be a bound to other parameters or values after this phase is instantiated or added as a subfragment
    """

    duration_default = constants.XODT_MOLASSES_DURATION
    time_step_default = 1e-3

    urukuls = urukuls_molasses
    default_urukul_amplitudes_start = [1.0]
    default_urukul_amplitudes_end = [1.0]
    suservos = suservos_molasses + suservos_XODT

    # These must be overridden / rebound by consumer fragments otherwise not
    # much will happen. This is done so that all the phases can share the same
    # detuning / nominal setpoints. Use
    # self.bind_suservo_setpoint_params_to_default_beam_setter for this.
    default_urukul_nominal_frequencies = [0.0]
    default_suservo_nominal_setpoints = [0.0] * 6

    default_suservo_setpoint_multiples_start = (
        constants.XODT_MOLASSES_SETPOINT_MULTIPLES_START
    )
    default_suservo_setpoint_multiples_end = (
        constants.XODT_MOLASSES_SETPOINT_MULTIPLES_END
    )

    default_urukul_detunings_start = constants.XODT_MOLASSES_689_DETUNING_START
    default_urukul_detunings_end = constants.XODT_MOLASSES_689_DETUNING_END

    # Chamber 2 bias coils in amps
    general_setter_default_starts = constants.XODT_MOLASSES_BIAS_FIELD_START
    general_setter_default_ends = constants.XODT_MOLASSES_BIAS_FIELD_END


class MolassesInXODT_2(MolassesInXODT):
    """
    A 2nd molasses phase with ramps for 689 nm molasses beams, a 1064/813 nm XODT, and bias fields

    We only define a single set of ramp parameters (unlike in the red MOT ramping phases) because we will probably only use this phase on Sr87

    The default suservo and urukul frequency "nominals" are set to zero at this point: To use these beams, they must be a bound to other parameters or values after this phase is instantiated or added as a subfragment
    """

    duration_default = constants.XODT_2ND_MOLASSES_DURATION
    default_suservo_setpoint_multiples_start = (
        constants.XODT_2ND_MOLASSES_SETPOINT_MULTIPLES_START
    )
    default_suservo_setpoint_multiples_end = (
        constants.XODT_2ND_MOLASSES_SETPOINT_MULTIPLES_END
    )

    default_urukul_detunings_start = constants.XODT_2ND_MOLASSES_689_DETUNING_START
    default_urukul_detunings_end = constants.XODT_2ND_MOLASSES_689_DETUNING_END

    # Chamber 2 bias coils in amps
    general_setter_default_starts = constants.XODT_2ND_MOLASSES_BIAS_FIELD_START
    general_setter_default_ends = constants.XODT_2ND_MOLASSES_BIAS_FIELD_END


class XODTWithFieldRamp(GeneralRampingPhaseWithBindingAndBiasField):
    """
    A phase with ramps for 1064/813 nm XODT and bias fields
    """

    duration_default = constants.XODT_EVAP_AND_FIELD_RAMP_DURATION
    time_step_default = 1e-3

    suservos = suservos_XODT

    # These must be overridden / rebound by consumer fragments otherwise not
    # much will happen. This is done so that all the phases can share the same
    # detuning / nominal setpoints. Use
    # self.bind_suservo_setpoint_params_to_default_beam_setter for this.
    default_suservo_nominal_setpoints = [0.0] * len(suservos_XODT)
    # The start setpoints must be overridden by daisy-chaining to previous phase
    default_suservo_setpoint_multiples_start = [0] * len(suservos_XODT)
    default_suservo_setpoint_multiples_end = (
        constants.XODT_EVAP_AND_FIELD_RAMP_SUSERVOS_END
    )

    # Chamber 2 bias coils in amps
    general_setter_default_starts = constants.XODT_EVAP_AND_FIELD_RAMP_FIELD_START
    general_setter_default_ends = constants.XODT_EVAP_AND_FIELD_RAMP_FIELD_END


class XODTWithLinearRamp(GeneralRampingPhaseWithBinding):
    """
    A phase with linear ramps for 1064 and 813 nm XODT
    """

    duration_default = 500e-3
    time_step_default = 1e-3

    suservos = suservos_XODT

    # self.bind_suservo_setpoint_params_to_default_beam_setter for this.
    default_suservo_nominal_setpoints = [3.5] * len(suservos_XODT)

    default_suservo_setpoint_multiples_start = constants.XODT_EVAP_START
    default_suservo_setpoint_multiples_end = constants.XODT_EVAP_END
