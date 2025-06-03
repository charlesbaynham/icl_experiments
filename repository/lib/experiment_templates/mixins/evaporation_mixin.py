from artiq.language import delay
from artiq.language import kernel
from ndscan.experiment.parameters import FloatParam
from ndscan.experiment.parameters import FloatParamHandle

import repository.lib.constants as constants
from repository.lib.experiment_templates.dipole_trap_experiment import (
    DipoleTrapWithExperiment,
)
from repository.lib.fragments.dipole_trap.dipole_trap_phases import SUSERVOS_XODT
from repository.lib.fragments.dipole_trap.dipole_trap_phases import XODTWithLinearRamp
from repository.lib.fragments.dipole_trap.dipole_trap_phases import XODTWithLinearRamp_2
from repository.lib.fragments.dipole_trap.dipole_trap_phases import XODTWithLinearRamp_3


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

        self.setattr_param(
            "total_evap_hold_time",
            FloatParam,
            "Duration of total evaporation",
            default=constants.TOTAL_EVAP_HOLD_TIME,
            min=0.0,
            unit="s",
        )
        self.total_evap_hold_time: FloatParamHandle

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
        delay(self.total_evap_hold_time.get() - self.linear_evap_ramp.duration.get())


class EvaporationThreeRampsMixin(EvaporationSingleRampMixin):
    """
    Loads atoms into a dipole trap after the narrowband red MOT, and implements a
    three stages of ramping dipole trap power.

    Kernel hooks used (multiple mixins cannot use the same hooks):

    * :meth:`~DMA_initialization_hook`
    * :meth:`~dipole_trap_evaporation_hook`
    """

    def build_fragment(self):
        super().build_fragment()

        self.setattr_fragment(
            "linear_evap_ramp_2",
            XODTWithLinearRamp_2,
            enforce_binding_to_defaults=False,
        )
        self.linear_evap_ramp_2: XODTWithLinearRamp_2

        self.setattr_fragment(
            "linear_evap_ramp_3",
            XODTWithLinearRamp_3,
            enforce_binding_to_defaults=False,
        )
        self.linear_evap_ramp_3: XODTWithLinearRamp_3

        self.linear_evap_ramp_2.daisy_chain_with_previous_phase(
            self.linear_evap_ramp, suservos=SUSERVOS_XODT
        )

        self.linear_evap_ramp_3.daisy_chain_with_previous_phase(
            self.linear_evap_ramp_2, suservos=SUSERVOS_XODT
        )

    @kernel
    def DMA_initialization_hook_linear_evap(self):
        self.linear_evap_ramp.precalculate_dma_handle()
        self.linear_evap_ramp_2.precalculate_dma_handle()
        self.linear_evap_ramp_3.precalculate_dma_handle()

    @kernel
    def DMA_initialization_hook(self):
        self.DMA_initialization_hook_default()
        self.DMA_initialization_hook_linear_evap()

    @kernel
    def dipole_trap_evaporation_hook(self):
        self.dipole_trap_evaporation_hook_default()
        self.linear_evap_ramp.do_phase()
        self.linear_evap_ramp_2.do_phase()
        self.linear_evap_ramp_3.do_phase()

        # hold the final trap to get a known total evaporation time
        duration_1 = self.linear_evap_ramp.duration.get()
        duration_2 = self.linear_evap_ramp_2.duration.get()
        duration_3 = self.linear_evap_ramp_3.duration.get()
        hold_time = self.total_evap_hold_time.get()

        if hold_time > duration_1 + duration_2 + duration_3:
            delay(hold_time - duration_1 - duration_2 - duration_3)
