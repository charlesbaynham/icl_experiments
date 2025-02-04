import logging

from artiq.experiment import kernel
from ndscan.experiment.entry_point import make_fragment_scan_exp
from ndscan.experiment.parameters import FloatParam
from ndscan.experiment.parameters import FloatParamHandle
import repository.lib.constants as constants

from repository.lib.fragments.dipole_trap.dipole_trap_phases import XODTWithLinearRamp
from repository.lib.experiment_templates.dipole_trap_experiment import (
    DipoleTrapWithExperiment,
)


class EvaporationMixin(DipoleTrapWithExperiment):
    def build_fragment(self):
        super().build_fragment()

        self.setattr_fragment(
            "linear_evap_ramp", XODTWithLinearRamp, enforce_binding_to_defaults=False
        )
        self.linear_evap_ramp: XODTWithLinearRamp

        # self.linear_evap_ramp.bind_suservo_setpoint_params_to_default_beam_setter(
        #   [self.dipole_beam_controller.all_beam_default_setter]
        # )

        # self.linear_evap_ramp.daisy_chain_with_previous_phase(self.narrow_red_compression_phase, suservos= suservos_XODT)
        self.linear_evap_ramp.default_suservo_setpoint_multiples_start = (
            constants.XODT_EVAP_START
        )
        self.linear_evap_ramp.default_suservo_setpoint_multiples_end = (
            constants.XODT_EVAP_END
        )

    @kernel
    def dipole_trap_evaporation_hook(self):
        self.linear_evap_ramp.do_phase()
