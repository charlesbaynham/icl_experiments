"""
Define the phases available in the dipole trap.
"""

import repository.lib.constants as constants
from repository.lib.fragments.ramping_phase_bound import GeneralRampingPhaseWithBinding
from repository.lib.fragments.ramping_phase_bound import (
    GeneralRampingPhaseWithBindingAndBiasField,
)

SUSERVOS_MOLASSES = [
    "red_mot_diagonal",
    "red_mot_sigmaplus",
    "red_mot_sigmaminus",
    "red_up",
]
URUKULS_MOLASSES = [
    "red_doublepass_injection",
]

# FIXME: Unused
# SUSERVOS_OPTICAL_PUMPING = [
#     "suservo_aom_singlepass_689_red_mot_sigmaplus",
#     "suservo_aom_singlepass_689_red_mot_sigmaminus",
# ]
# URUKULS_OPTICAL_PUMPING = ["urukul9910_aom_doublepass_689_red_spinpol"]

SUSERVOS_XODT = [
    "dipole_trap_1064_delivery",
    "down_813",
]
SUSERVOS_TRANSPARENCY = ["blue_transparency_beam"]


SUSERVOS_MOLASSES_DEVICES = [
    constants.SUSERVOED_BEAMS[b].suservo_device for b in SUSERVOS_MOLASSES
]
SUSERVOS_XODT_DEVICES = [
    constants.SUSERVOED_BEAMS[b].suservo_device for b in SUSERVOS_XODT
]
SUSERVOS_TRANSPARENCY_DEVICES = [
    constants.SUSERVOED_BEAMS[b].suservo_device for b in SUSERVOS_TRANSPARENCY
]

URUKULS_MOLASSES_DEVICES = [
    constants.URUKULED_BEAMS[b].urukul_device for b in URUKULS_MOLASSES
]

# Unused
# SUSERVOS_CAVITY_LATTICE = [
#     "suservo_aom_singlepass_1379_cavity_input",
# ]


class MOTInSingleXODT(GeneralRampingPhaseWithBinding):
    """
    A MOT phase with ramps for the MOT beams and a 1064/813 XODT.

    This has no field ramping because it is used for loading a single XODT
    """

    duration_default = constants.XODT_SINGLE_LOADING_DURATION
    time_step_default = 1e-3

    urukuls = URUKULS_MOLASSES_DEVICES
    default_urukul_amplitudes_start = [1.0]
    default_urukul_amplitudes_end = [1.0]

    suservos = SUSERVOS_MOLASSES_DEVICES + SUSERVOS_XODT_DEVICES

    # These must be overridden / rebound by consumer fragments otherwise not
    # much will happen. This is done so that all the phases can share the same
    # detuning / nominal setpoints. Use
    # self.bind_suservo_setpoint_params_to_default_beam_setter for this.
    default_urukul_nominal_frequencies = [0.0]
    default_suservo_nominal_setpoints = [0.0] * 6

    # Look up the photodiode offsets and PGIA settings for the lower-power
    # beams. In future we might specify these for all beams, but for now we
    # prefer to just put it in for the low power ones since this is the only
    # place we need it.
    suservo_offsets, suservo_pgias = zip(
        *[
            (
                (0.0, 0.0)
                if beam_name not in constants.SUSERVOED_BEAMS_LOW_INTENSITY
                else (
                    constants.SUSERVOED_BEAMS_LOW_INTENSITY[
                        beam_name
                    ].photodiode_offset,
                    constants.SUSERVOED_BEAMS_LOW_INTENSITY[beam_name].pgia_setting,
                )
            )
            for beam_name in SUSERVOS_MOLASSES + SUSERVOS_XODT
        ]
    )

    default_suservo_setpoint_multiples_start = (
        constants.XODT_SINGLE_LOADING_SETPOINT_MULTIPLES_START
    )
    default_suservo_setpoint_multiples_end = (
        constants.XODT_SINGLE_LOADING_SETPOINT_MULTIPLES_END
    )

    default_urukul_detunings_start = [0.0]
    default_urukul_detunings_end = [0.0]


class MolassesInXODT(GeneralRampingPhaseWithBindingAndBiasField):
    """
    A molasses phase with ramps for 689 nm molasses beams, a 1064/813 nm XODT,
    and bias fields

    We only define a single set of ramp parameters (unlike in the red MOT
    ramping phases) because we will probably only use this phase on Sr87

    The default suservo and urukul frequency "nominals" are set to zero at this
    point: To use these beams, they must be a bound to other parameters or
    values after this phase is instantiated or added as a subfragment
    """

    duration_default = constants.XODT_MOLASSES_DURATION
    time_step_default = 1e-3

    urukuls = URUKULS_MOLASSES_DEVICES
    default_urukul_amplitudes_start = [1.0]
    default_urukul_amplitudes_end = [1.0]
    suservos = (
        SUSERVOS_MOLASSES_DEVICES
        + SUSERVOS_XODT_DEVICES
        + SUSERVOS_TRANSPARENCY_DEVICES
    )

    # These must be overridden / rebound by consumer fragments otherwise not
    # much will happen. This is done so that all the phases can share the same
    # detuning / nominal setpoints. Use
    # self.bind_suservo_setpoint_params_to_default_beam_setter for this.
    default_urukul_nominal_frequencies = [0.0]
    default_suservo_nominal_setpoints = [0.0] * len(suservos)
    suservo_offsets = [0.0] * len(suservos)
    suservo_pgias = [0] * len(suservos)

    for idx, beam_name in enumerate(suservos):
        for beam_info in constants.SUSERVOED_BEAMS_LOW_INTENSITY:
            if (
                constants.SUSERVOED_BEAMS_LOW_INTENSITY[beam_info].suservo_device
                == beam_name
            ):
                suservo_offsets[idx] = constants.SUSERVOED_BEAMS_LOW_INTENSITY[
                    beam_info
                ].photodiode_offset
                suservo_pgias[idx] = constants.SUSERVOED_BEAMS_LOW_INTENSITY[
                    beam_info
                ].pgia_setting
                break

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
    A 2nd molasses phase with ramps for 689 nm molasses beams, a 1064/813 nm
    XODT, and bias fields

    We only define a single set of ramp parameters (unlike in the red MOT
    ramping phases) because we will probably only use this phase on Sr87
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

    suservos = SUSERVOS_XODT_DEVICES

    # These must be overridden / rebound by consumer fragments otherwise not
    # much will happen. This is done so that all the phases can share the same
    # detuning / nominal setpoints. Use
    # self.bind_suservo_setpoint_params_to_default_beam_setter for this.
    default_suservo_nominal_setpoints = [0.0] * len(SUSERVOS_XODT)
    # The start setpoints must be overridden by daisy-chaining to previous phase
    default_suservo_setpoint_multiples_start = [0] * len(SUSERVOS_XODT)
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
    time_step_default = 40e-3

    suservos = SUSERVOS_XODT_DEVICES

    # self.bind_suservo_setpoint_params_to_default_beam_setter for this.
    default_suservo_nominal_setpoints = [0.0] * len(SUSERVOS_XODT)

    default_suservo_setpoint_multiples_start = constants.XODT_EVAP_START
    default_suservo_setpoint_multiples_end = constants.XODT_EVAP_END

    # add_final_point = True


class XODTWithLinearRamp_2(XODTWithLinearRamp):
    """
    A second phase with linear ramps for 1064 and 813 nm XODT
    """

    duration_default = 500e-3

    default_suservo_setpoint_multiples_start = constants.XODT_EVAP_2_START
    default_suservo_setpoint_multiples_end = constants.XODT_EVAP_2_END


class XODTWithLinearRamp_3(XODTWithLinearRamp):
    """
    A third phase with linear ramps for 1064 and 813 nm XODT
    """

    duration_default = 500e-3

    default_suservo_setpoint_multiples_start = constants.XODT_EVAP_3_START
    default_suservo_setpoint_multiples_end = constants.XODT_EVAP_3_END

    add_final_point = True
