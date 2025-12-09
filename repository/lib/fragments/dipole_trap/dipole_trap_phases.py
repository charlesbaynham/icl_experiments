"""
Define the phases available in the dipole trap.
"""

import logging

import repository.lib.constants as constants
from repository.lib.fragments.ramping_phase_bound import GeneralRampingPhaseWithBinding
from repository.lib.fragments.ramping_phase_bound import (
    GeneralRampingPhaseWithBindingAndBiasField,
)

logger = logging.getLogger(__name__)

SUSERVOS_RED = [
    "suservo_aom_singlepass_689_red_mot_diagonal",
    "suservo_aom_singlepass_689_red_mot_sigmaplus",
    "suservo_aom_singlepass_689_red_mot_sigmaminus",
    "suservo_aom_singlepass_689_up",
]
SUSERVO_MOLASSES = ["suservo_aom_singlepass_689_molasses"]
URUKUL_RED_IJD = ["urukul9910_aom_doublepass_689_red_injection"]

SUSERVOS_OPTICAL_PUMPING = [
    "suservo_aom_singlepass_689_red_mot_sigmaplus",
    "suservo_aom_singlepass_689_red_mot_sigmaminus",
]
URUKULS_OPTICAL_PUMPING = ["urukul9910_aom_doublepass_689_red_spinpol"]

SUSERVOS_XODT = [
    "suservo_aom_1064_delivery",
    "suservo_aom_down_813",
]

SUSERVO_PAINTER = [
    "suservo_aom_1064_painted_delivery"
]

SUSERVOS_TRANSPARENCY = ["suservo_aom_singlepass_487_transparency"]

SUSERVOS_CAVITY_LATTICE = [
    "suservo_aom_singlepass_1379_cavity_input",
]


class _RedAndXODTBeamsBase(GeneralRampingPhaseWithBinding):
    """
    Ramp stage for the red MOT beams and the XODT beams, with the red MOT beams
    set to "low power mode" (i.e. their PGIA has been boosted)
    """

    time_step_default = 1e-3

    urukuls = URUKUL_RED_IJD
    default_urukul_amplitudes_start = [1.0]
    default_urukul_amplitudes_end = [1.0]
    suservos = SUSERVOS_RED + SUSERVOS_XODT

    # These must be overridden / rebound by consumer fragments otherwise not
    # much will happen. This is done so that all the phases can share the same
    # detuning / nominal setpoints. Use
    # self.bind_suservo_setpoint_params_to_default_beam_setter for this.
    default_urukul_nominal_frequencies = [0.0]

    def __init__(self, *args, **kwargs):
        # Look up the photodiode offsets, PGIA settings and IIR kI coefficients for the lower-power
        # beams. If a beam is not in the list, default to the values for the normal beams.
        #
        # Do this in the constructor so that it pays attention to the beam names
        # if they have been changed by child classes
        combined_beaminfos_for_low_power = constants.SUSERVOED_BEAMS.copy()
        combined_beaminfos_for_low_power.update(constants.SUSERVOED_BEAMS_LOW_INTENSITY)

        logger.debug("constants.SUSERVOED_BEAMS: %s", constants.SUSERVOED_BEAMS)
        logger.debug(
            "constants.SUSERVOED_BEAMS_LOW_INTENSITY: %s",
            constants.SUSERVOED_BEAMS_LOW_INTENSITY,
        )
        logger.debug(
            "combined_beaminfos_for_low_power: %s", combined_beaminfos_for_low_power
        )

        suservo_beaminfos_by_devicename = {
            info.suservo_device: info
            for info in combined_beaminfos_for_low_power.values()
        }

        self.default_suservo_pgias = [
            suservo_beaminfos_by_devicename[device_name].pgia_setting
            for device_name in self.suservos
        ]
        self.default_suservo_kIs = [
            suservo_beaminfos_by_devicename[device_name].kI_loop_constant
            for device_name in self.suservos
        ]

        self.suservo_offsets = [
            suservo_beaminfos_by_devicename[device_name].photodiode_offset
            for device_name in self.suservos
        ]

        # Specify the SUServo nominal setpoints like this too for the same
        # reason (i.e. because we currently sometimes want the transparency beam
        # and sometimes don't). These will be rebound anyway
        self.default_suservo_nominal_setpoints = [0.0] * len(self.suservos)

        super().__init__(*args, **kwargs)


class MOTInSingleXODT(_RedAndXODTBeamsBase):
    """
    A MOT phase with ramps for the MOT beams and a 1064/813 XODT.

    This has no field ramping because it is used for loading a single XODT

    This is optimized to transfer a red MOT into a single XODT
    """

    duration_default = constants.XODT_SINGLE_LOADING_DURATION

    default_suservo_setpoint_multiples_start = (
        constants.XODT_SINGLE_LOADING_SETPOINT_MULTIPLES_START
    )
    default_suservo_setpoint_multiples_end = (
        constants.XODT_SINGLE_LOADING_SETPOINT_MULTIPLES_END
    )

    default_urukul_detunings_start = constants.XODT_SINGLE_LOADING_689_DETUNING_START
    default_urukul_detunings_end = constants.XODT_SINGLE_LOADING_689_DETUNING_END


class MOTInBottomXODT(_RedAndXODTBeamsBase):
    """
    Make a MOT on the backward XODT

    This phase will be used after :class:`~MOTInSingleXODT`, so atoms will
    already be in the top trap. We therefore cannot turn off the XODT beams, so
    leave them alone.

    This also ignores the magnetic field, assuming that it has been set to the
    right value already. We could add a ramp instead, maybe it would help.
    """

    duration_default = constants.XXODT_LOWER_LOADING_DURATION

    suservos = SUSERVOS_RED

    default_suservo_setpoint_multiples_start = (
        constants.XXODT_LOWER_LOADING_SETPOINT_MULTIPLES_START
    )
    default_suservo_setpoint_multiples_end = (
        constants.XXODT_LOWER_LOADING_SETPOINT_MULTIPLES_END
    )

    default_urukul_detunings_start = [0.0]
    default_urukul_detunings_end = [0.0]


class MolassesRetroed(GeneralRampingPhaseWithBindingAndBiasField):
    """
    Molasses phase with retro-reflected 689 nm molasses beams
    """

    time_step_default = 1e-3
    duration_default = constants.XODT_MOLASSES_DURATION

    urukuls = URUKULS_OPTICAL_PUMPING
    default_urukul_amplitudes_start = [1.0]
    default_urukul_amplitudes_end = [1.0]
    suservos = SUSERVO_MOLASSES + SUSERVOS_XODT

    # These must be overridden / rebound by consumer fragments otherwise not
    # much will happen. This is done so that all the phases can share the same
    # detuning / nominal setpoints. Use
    # self.bind_suservo_setpoint_params_to_default_beam_setter for this.
    default_urukul_nominal_frequencies = [0.0]
    default_urukul_detunings_start = [0.0]
    default_urukul_detunings_end = [0.0]

    # These must be overridden / rebound by consumer fragments otherwise not
    # much will happen. This is done so that all the phases can share the same
    # detuning / nominal setpoints. Use
    # self.bind_suservo_setpoint_params_to_default_beam_setter for this.
    default_suservo_nominal_setpoints = [0.0] * len(SUSERVO_MOLASSES + SUSERVOS_XODT)
    # The start setpoints must be overridden by daisy-chaining to previous phase
    default_suservo_setpoint_multiples_start = [1] * len(
        SUSERVO_MOLASSES + SUSERVOS_XODT
    )
    default_suservo_setpoint_multiples_end = [1] * len(SUSERVO_MOLASSES + SUSERVOS_XODT)

    # Chamber 2 bias coils in amps
    general_setter_default_starts = constants.XODT_MOLASSES_BIAS_FIELD_START
    general_setter_default_ends = constants.XODT_MOLASSES_BIAS_FIELD_END


class MolassesInXODT(_RedAndXODTBeamsBase, GeneralRampingPhaseWithBindingAndBiasField):
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

    suservos = SUSERVOS_RED + SUSERVOS_XODT + SUSERVOS_TRANSPARENCY

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


class EvapFieldRamp(GeneralRampingPhaseWithBindingAndBiasField):
    """
    A phase that just ramps the bias field in the evaporation stage, from the
    spin pol settings to the clock spec settings
    """

    duration_default = constants.XODT_EVAP_AND_FIELD_RAMP_DURATION
    time_step_default = 1e-3

    suservos = []

    # Chamber 2 bias coils in amps
    #
    # N.B. The start values are ignored if there is a spin pol phase present -
    # the spin pol settings are used instead.
    general_setter_default_starts = constants.XODT_EVAP_AND_FIELD_RAMP_FIELD_START
    general_setter_default_ends = constants.XODT_EVAP_AND_FIELD_RAMP_FIELD_END


class XODTWithFieldAndIntensityRamp(
    EvapFieldRamp, GeneralRampingPhaseWithBindingAndBiasField
):
    """
    A phase with ramps for 1064/813 nm XODT and bias fields
    """

    suservos = SUSERVOS_XODT

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


class MolassesDipoleRamp(GeneralRampingPhaseWithBinding):
    """
    A phase with linear ramps for 1064 and 813 nm XODT
    """

    duration_default = 1400e-3
    time_step_default = 1e-3

    suservos = SUSERVOS_XODT + SUSERVO_PAINTER

    # self.bind_suservo_setpoint_params_to_default_beam_setter for this.
    # Hmm I've changed the argument in len() from SUSERVOS_XODT -> suservos to encompass the painter, I think that's ok.
    default_suservo_nominal_setpoints = [0.0] * len(suservos)

    default_suservo_setpoint_multiples_start = (
        constants.XODT_COOL_MOLASSES_MULTIPLE_START
    )
    default_suservo_setpoint_multiples_end = constants.XODT_COOL_MOLASSES_MULTIPLE_END


class XODTWithLinearRamp(GeneralRampingPhaseWithBinding):
    """
    A phase with linear ramps for 1064 and 813 nm XODT
    """

    duration_default = constants.XODT_EVAP_DURATION
    time_step_default = 40e-3

    suservos = SUSERVOS_XODT

    # self.bind_suservo_setpoint_params_to_default_beam_setter for this.
    default_suservo_nominal_setpoints = [0.0] * len(SUSERVOS_XODT)

    default_suservo_setpoint_multiples_start = constants.XODT_EVAP_START
    default_suservo_setpoint_multiples_end = constants.XODT_EVAP_END

    # add_final_point = True


class XODTWithLinearRamp_2(XODTWithLinearRamp):
    """
    A second phase with linear ramps for 1064 and 813 nm XODT
    """

    duration_default = constants.XODT_EVAP_2_DURATION

    default_suservo_setpoint_multiples_start = [0.0] * 2
    default_suservo_setpoint_multiples_end = constants.XODT_EVAP_2_END


class XODTWithLinearRamp_3(XODTWithLinearRamp):
    """
    A third phase with linear ramps for 1064 and 813 nm XODT
    """

    duration_default = constants.XODT_EVAP_3_DURATION

    default_suservo_setpoint_multiples_start = [0.0] * 2
    default_suservo_setpoint_multiples_end = constants.XODT_EVAP_3_END

    add_final_point = True


class DipoleRamp1064(GeneralRampingPhaseWithBinding):
    """
    A phase with linear ramp for 1064
    """

    duration_default = 20e-3
    time_step_default = 1e-3

    suservos = ["suservo_aom_1064_delivery"]

    # self.bind_suservo_setpoint_params_to_default_beam_setter for this.
    default_suservo_nominal_setpoints = [0.0]

    default_suservo_setpoint_multiples_start = [0.0]
    default_suservo_setpoint_multiples_end = [1.0]
