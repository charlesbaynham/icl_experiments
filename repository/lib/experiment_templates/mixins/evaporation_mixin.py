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


class EvaporationSingleRampMixin(DipoleTrapWithExperiment):
    """
    Loads atoms into a dipole trap after the narrowband red MOT, and implements a
    single stage of ramping dipole trap power.

    Kernel hooks used (multiple mixins cannot use the same hooks):

    * :meth:`~DMA_initialization_hook`
    * :meth:`~dipole_trap_evaporation_hook`
    """   
    def build_fragment(self):
        super().build_fragment()

        self.setattr_fragment(
            "linear_evap_ramp", XODTWithLinearRamp, enforce_binding_to_defaults=False
        )
        self.linear_evap_ramp: XODTWithLinearRamp

        self.linear_evap_ramp.bind_suservo_setpoint_params_to_default_beam_setter(
            [self.dipole_beam_controller.all_beam_default_setter]
        )

    @kernel
    def DMA_initialization_hook_linear_evap(self):
        self.linear_evap_ramp.precalculate_dma_handle()

    @kernel
    def DMA_initialization_hook(self):
        self.DMA_initialization_hook_default()
        self.DMA_initialization_hook_linear_evap()

    @kernel
    def dipole_trap_evaporation_hook(self):
        self.dipole_trap_evaporation_hook_default()
        self.linear_evap_ramp.do_phase()

