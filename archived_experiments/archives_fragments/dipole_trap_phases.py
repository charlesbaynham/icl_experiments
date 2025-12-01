import logging

import repository.lib.constants as constants
from repository.lib.fragments.ramping_phase_bound import GeneralRampingPhaseWithBinding

from repository.lib.fragments.dipole_trap.dipole_trap_phases import MolassesInXODT

logger = logging.getLogger(__name__)


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
