import abc

from artiq.language import delay
from artiq.language import kernel
from ndscan.experiment.parameters import BoolParam
from ndscan.experiment.parameters import BoolParamHandle
from ndscan.experiment.parameters import FloatParam
from ndscan.experiment.parameters import FloatParamHandle
from pyaion.fragments.ramping_phase import GeneralRampingPhase

import repository.lib.constants as constants
from repository.lib.experiment_templates.dipole_trap_experiment import (
    DipoleTrapWithExperiment,
)
from repository.lib.experiment_templates.mixins.optical_pumping import (
    OpticalPumpingWithFieldSettingBase,
)
from repository.lib.fragments.dipole_trap.dipole_trap_phases import SUSERVOS_XODT
from repository.lib.fragments.dipole_trap.dipole_trap_phases import EvapFieldRamp
from repository.lib.fragments.dipole_trap.dipole_trap_phases import (
    XODTWithFieldAndIntensityRamp,
)
from repository.lib.fragments.dipole_trap.dipole_trap_phases import XODTWithLinearRamp
from repository.lib.fragments.dipole_trap.dipole_trap_phases import XODTWithLinearRamp_2
from repository.lib.fragments.dipole_trap.dipole_trap_phases import XODTWithLinearRamp_3


class _RampDuringEvapHookBase(DipoleTrapWithExperiment, abc.ABC):
    """
    Framework for implementing a ramping phase during the evaporation phase

    This is generalised so that we can have either evaporation + field ramping, or only field ramping

    This is a mixin - see the documentation for :mod:`~.dipole_trap_experiment` for
    details.

    Kernel hooks used (multiple mixins cannot use the same hooks):

    * :meth:`~DMA_initialization_hook`
    * :meth:`~dipole_trap_evaporation_hook`
    """

    ramp_during_evap_phase: GeneralRampingPhase

    def build_fragment(self):
        super().build_fragment()

        self._define_evap_phase_ramp()

        # If we have a spin pol stage, bind the field start values to the end of
        # the spin pol stage
        if isinstance(self, OpticalPumpingWithFieldSettingBase):
            for l in "xyz":
                # This code is fragile because it relies on strings, but it
                # should break with an error if the strings change so the unit
                # tests will catch it:
                self.ramp_during_evap_phase.bind_param(
                    param_name=f"bias_field_{l}_start",
                    source=getattr(self, f"bias_{l}_for_pumping"),
                )

    @abc.abstractmethod
    def _define_evap_phase_ramp(self):
        pass

    @kernel
    def DMA_initialization_hook_evap_with_field_ramp(self):
        self.ramp_during_evap_phase.precalculate_dma_handle()

    @kernel
    def DMA_initialization_hook(self):
        raise NotImplementedError(
            "All the DMA handle calculations must be combined into one \
                DMA_initialization_hook() method after Mixins are combined"
        )

    @kernel
    def dipole_trap_evaporation_hook_ramper(self):
        """
        Do the evap / field ramp phase
        """
        self.ramp_during_evap_phase.do_phase()

    @kernel
    def dipole_trap_evaporation_hook(self):
        # Default hook turns off red beams - good!
        self.dipole_trap_evaporation_hook_default()
        self.dipole_trap_evaporation_hook_ramper()


class EvapAndFieldRampBase(_RampDuringEvapHookBase):
    """
    Exposes the evaporation and field ramping phase for use in evaporation Mixins
    """

    def build_fragment(self):
        super().build_fragment()

        self.ramp_during_evap_phase.bind_suservo_setpoint_params_to_default_beam_setter(
            [self.dipole_beam_controller.all_beam_default_setter]
        )

    def _define_evap_phase_ramp(self):
        self.setattr_fragment(
            "ramp_during_evap_phase",
            XODTWithFieldAndIntensityRamp,
        )
        self.ramp_during_evap_phase: XODTWithFieldAndIntensityRamp


class FieldOnlyRampInEvapMixin(_RampDuringEvapHookBase):
    """
    Ramps the magnetic field during the evaporation phase, but with no actual
    evaporation
    """

    def _define_evap_phase_ramp(self):
        self.setattr_fragment(
            "ramp_during_evap_phase",
            EvapFieldRamp,
        )
        self.ramp_during_evap_phase: EvapFieldRamp


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
        if self.linear_evap_ramp.duration.get() < self.total_evap_hold_time.get():
            # hold the final trap to get a known total evaporation time
            # if the ramp is shorter than the hold time, delay for the difference
            delay(
                self.total_evap_hold_time.get() - self.linear_evap_ramp.duration.get()
            )


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

        self.setattr_param(
            "evap_bool",
            BoolParam,
            "Do evaporation?",
            default=True,
        )
        self.evap_bool: BoolParamHandle

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
        if self.evap_bool.get():
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
        else:
            self.dipole_trap_evaporation_hook_default()


class EvaporationThreeRampsWithFieldRampMixin(EvapAndFieldRampBase):
    """
    Loads atoms into a dipole trap after the narrowband red MOT, and implements a
    three stages of ramping dipole trap power, with a field ramp during evaporation.

    Kernel hooks used (multiple mixins cannot use the same hooks):

    * :meth:`~DMA_initialization_hook`
    * :meth:`~dipole_trap_evaporation_hook`
    """

    def build_fragment(self):
        super().build_fragment()

        self.setattr_fragment(
            "field_only_ramp",
            EvapFieldRamp,
        )
        self.field_only_ramp: EvapFieldRamp

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
            self.ramp_during_evap_phase, suservos=SUSERVOS_XODT
        )

        self.linear_evap_ramp_3.daisy_chain_with_previous_phase(
            self.linear_evap_ramp_2, suservos=SUSERVOS_XODT
        )

        self.setattr_param(
            "evap_bool",
            BoolParam,
            "Do evaporation?",
            default=True,
        )
        self.evap_bool: BoolParamHandle

    @kernel
    def DMA_initialization_hook_evap_with_field_ramp(self):
        self.ramp_during_evap_phase.precalculate_dma_handle()
        self.linear_evap_ramp_2.precalculate_dma_handle()
        self.linear_evap_ramp_3.precalculate_dma_handle()

    @kernel
    def DMA_initialization_hook(self):
        self.DMA_initialization_hook_default()
        self.DMA_initialization_hook_evap_with_field_ramp(self)

    @kernel
    def dipole_trap_evaporation_hook(self):
        if self.evap_bool.get():
            self.dipole_trap_evaporation_hook_default()
            self.ramp_during_evap_phase.do_phase()
            self.linear_evap_ramp_2.do_phase()
            self.linear_evap_ramp_3.do_phase()

        else:
            self.dipole_trap_evaporation_hook_default()
            self.field_only_ramp.do_phase()
