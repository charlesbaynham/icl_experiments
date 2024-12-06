import logging

from artiq.experiment import delay
from artiq.experiment import delay_mu
from artiq.experiment import kernel
from ndscan.experiment.parameters import FloatParam
from ndscan.experiment.parameters import FloatParamHandle
from numpy import int64

from repository.lib import constants
from repository.lib.experiment_templates.dipole_trap_experiment import (
    DipoleTrapWithExperiment,
)
from repository.lib.fragments.dipole_trap.dipole_trap_phases import MolassesInXODT
from repository.lib.fragments.dipole_trap.dipole_trap_phases import MolassesInXODT_2
from repository.lib.fragments.dipole_trap.dipole_trap_phases import XODTWithFieldRamp
from repository.lib.fragments.dipole_trap.dipole_trap_phases import suservos_XODT

logger = logging.getLogger(__name__)


class XODTSingleMolassesMixin(DipoleTrapWithExperiment):
    """
    Loads atoms into a dipole trap after the narrowband red MOT, and implements a
    single stage of ramping molasses (or MOT) with ramping bias magnetic field.

    Kernel hooks used (multiple mixins cannot use the same hooks):

    * :meth:`~DMA_initialization_hook`
    * :meth:`~before_start_hook`
    * :meth:`~post_narrowband_hook`
    * :meth:`~dipole_trap_molasses_hook`

    We also override this hook to do nothing since this Mixin is now taking charge
    of field setting:

    * :meth:`~set_postnarrowband_fields_hook`
    """

    def build_fragment(self):
        super().build_fragment()

        self.setattr_fragment("molasses_xodt_1", MolassesInXODT)
        self.molasses_xodt_1: MolassesInXODT

        # Remove unused parameters
        self.override_param("spectroscopy_field_gradient", 0)

        # # Expose the bias field for moving the MOT to the right place
        self.setattr_param_rebind(
            "chamber_2_red_narrowband_mot_current_start",
            self.red_mot.narrow_red_compression_phase,
            original_name="chamber_2_mot_current_start",
            default=constants.RED_COMPRESSION_MOT_CURRENT_START_FOR_MOLASSES,
        )
        self.setattr_param_rebind(
            "chamber_2_red_narrowband_mot_current_end",
            self.red_mot.narrow_red_compression_phase,
            original_name="chamber_2_mot_current_end",
            default=constants.RED_COMPRESSION_MOT_CURRENT_END_FOR_MOLASSES,
        )
        for idx, axis in enumerate(["x", "y", "z"]):
            self.setattr_param_rebind(
                f"narrowband_bias_{axis}",
                self.red_mot,
                default=constants.BIAS_DURING_NARROWBAND_MOT_FOR_MOLASSES[idx],
            )
        self.setattr_param_rebind(
            "red_narrowband_mot_689_up_start",
            self.red_mot.narrow_red_compression_phase,
            original_name="setpoint_multiple_start_suservo_aom_singlepass_689_up",
            default=constants.RED_COMPRESSION_MOT_UP_BEAM_SETPOINT_FOR_MOLASSES,
        )
        self.setattr_param_rebind(
            "red_narrowband_mot_689_up_end",
            self.red_mot.narrow_red_compression_phase,
            original_name="setpoint_multiple_end_suservo_aom_singlepass_689_up",
        )

        self.setattr_param(
            "delay_before_molasses",
            FloatParam,
            "Time to hold in dipole trap before molasses starts",
            default=constants.DELAY_BEFORE_MOLASSES,
            unit="ms",
        )
        self.delay_before_molasses: FloatParamHandle

        self.setattr_param(
            "mot_coil_current_first_molasses",
            FloatParam,
            "MOT coil current during first molasses",
            default=constants.XODT_MOLASSES_MOT_CURRENT,
            unit="A",
            min=0,
            max=130,
        )
        self.mot_coil_current_first_molasses: FloatParamHandle

        self.setattr_param(
            "stir_beam_detuning_molasses_1",
            FloatParam,
            "Detuning of the 689 stir beam during 1st molasses",
            default=0,
            unit="kHz",
            min=-2e6,
            max=2e6,
        )
        self.stir_beam_detuning_molasses_1: FloatParamHandle

        self.molasses_xodt_1.bind_suservo_setpoint_params_to_default_beam_setter(
            [
                self.red_mot.red_beam_controller.all_beam_default_setter,
                self.dipole_beam_controller.all_beam_default_setter,
            ]
        )

        self.molasses_xodt_1.bind_ad9910_frequency_params(
            [self.red_mot.injection_aom_static_frequency]
        )

    @kernel
    def DMA_initialization_hook(self):
        self.DMA_initialization_hook_default()
        self.DMA_initialization_hook_xodt_molasses()

    @kernel
    def DMA_initialization_hook_xodt_molasses(self):
        """
        Preload phases' handles. These have to be grouped together, instead of
        handled in separate subfragment setups, otherwise only the last-compiled
        dma handle is valid.
        """
        self.molasses_xodt_1.precalculate_dma_handle()

    @kernel
    def before_start_hook(self):
        self.before_start_hook_xodt_molasses()

    @kernel
    def before_start_hook_xodt_molasses(self):
        """
        Before the blue MOT, turn on the crossed dipole trap beams and
        set setpoints to same as the start of the xodt molasses ramp.

        TODO: Move this to a device_setup / use a default beam setter to define setpoints
        """

        self.core.break_realtime()
        self.dipole_beam_controller.XODT_setter.turn_on_all()
        delay_mu(int64(self.core.ref_multiplier))
        self.core.break_realtime()
        self.dipole_beam_controller.set_dipole_suservo_setpoints(
            setpoint_down_813=self.molasses_xodt_1.default_suservo_setpoint_multiples_start[
                5
            ],
            setpoint_dipole_trap_1064_delivery=self.molasses_xodt_1.default_suservo_setpoint_multiples_start[
                4
            ],
        )

    @kernel
    def post_narrowband_hook(self):
        """
        Turn off red MOT beams (default hook), set coil currents, and wait
        """
        self.post_narrowband_hook_xodt_molasses()

    @kernel
    def set_postnarrowband_fields_hook(self):
        self.set_postnarrowband_fields_hook_singlemollasses()

    @kernel
    def set_postnarrowband_fields_hook_singlemollasses(self):
        pass

    @kernel
    def post_narrowband_hook_xodt_molasses(self):
        """
        Turn off MOT fields and set bias fields to molasses ramp start.

        Wait a settling time before starting the molasses.
        """
        self.red_mot.chamber_2_field_setter.set_all_fields(
            self.mot_coil_current_first_molasses.get(),
            self.molasses_xodt_1.general_setter_default_starts[0],
            self.molasses_xodt_1.general_setter_default_starts[1],
            self.molasses_xodt_1.general_setter_default_starts[2],
        )
        if self.delay_before_molasses.get() > 1e-6:
            self.red_mot.red_beam_controller.all_mot_beams_setter.turn_beams_off(
                ignore_shutters=True
            )
        delay(self.delay_before_molasses.get())

    @kernel
    def dipole_trap_molasses_hook(self):
        self.dipole_trap_molasses_hook_first_xodt_molasses()

    @kernel
    def dipole_trap_molasses_hook_first_xodt_molasses(self):
        """
        Do the first molasses ramping phase
        """
        self.red_mot.red_beam_controller.all_mot_beams_setter.turn_beams_on(
            ignore_shutters=True
        )

        # Step the 689 stir frequency
        self.blue_3d_mot.mirny_eom_sidebands.set_689_stir_sideband_detuning(
            detuning=self.stir_beam_detuning_molasses_1.get()
        )

        self.molasses_xodt_1.do_phase()


class XODTDoubleMolassesMixin(XODTSingleMolassesMixin):
    """
    Loads atoms into a dipole trap after the narrowband red MOT, and implements a
    single stage of ramping molasses (or MOT) with ramping bias magnetic field.

    Kernel hooks used (multiple mixins cannot use the same hooks):

    * :meth:`~DMA_initialization_hook`
    * :meth:`~before_start_hook`
    * :meth:`~post_narrowband_hook`
    * :meth:`~dipole_trap_molasses_hook`

    We also override this hook to do nothing since this Mixin is now taking charge
    of field setting:

    * :meth:`~set_postnarrowband_fields_hook`
    """

    def build_fragment(self):
        super().build_fragment()

        self.setattr_fragment(
            "molasses_xodt_2", MolassesInXODT_2, enforce_binding_to_defaults=False
        )
        self.molasses_xodt_2: MolassesInXODT_2

        self.setattr_param(
            "delay_between_molasses",
            FloatParam,
            "Delay time between molasses for field settling",
            default=constants.DELAY_BETWEEN_MOLASSES,
            unit="ms",
        )
        self.delay_between_molasses: FloatParamHandle

        self.setattr_param(
            "mot_coil_current_2nd_molasses",
            FloatParam,
            "MOT coil current during 2nd molasses",
            default=constants.XODT_2ND_MOLASSES_MOT_CURRENT,
            unit="A",
            min=0,
            max=130,
        )
        self.mot_coil_current_2nd_molasses: FloatParamHandle

        self.setattr_param(
            "stir_beam_detuning_molasses_2",
            FloatParam,
            "Detuning of the 689 stir beam during 2nd molasses",
            default=constants.XODT_2ND_MOLASSES_689_STIR_DETUNING,
            unit="kHz",
            min=-2e6,
            max=2e6,
        )
        self.stir_beam_detuning_molasses_2: FloatParamHandle

        self.molasses_xodt_2.bind_ad9910_frequency_params(
            [self.red_mot.injection_aom_static_frequency]
        )

        self.molasses_xodt_2.daisy_chain_with_previous_phase(
            self.molasses_xodt_1, suservos=suservos_XODT
        )

    @kernel
    def DMA_initialization_hook(self):
        self.DMA_initialization_hook_default()
        self.DMA_initialization_hook_xodt_molasses()

    @kernel
    def DMA_initialization_hook_xodt_molasses(self):
        """
        Preload phases' handles. These have to be grouped together, instead of
        handled in separate subfragment setups, otherwise only the last-compiled
        dma handle is valid.
        """
        self.molasses_xodt_1.precalculate_dma_handle()
        self.molasses_xodt_2.precalculate_dma_handle()

    @kernel
    def dipole_trap_molasses_hook(self):
        self.dipole_trap_molasses_hook_first_xodt_molasses()
        self.dipole_trap_molasses_hook_second_xodt_molasses()

    @kernel
    def dipole_trap_molasses_hook_second_xodt_molasses(self):
        """
        Do the second molasses ramping phase
        """
        # Set fields in advance of 2nd molasses
        self.red_mot.chamber_2_field_setter.set_all_fields(
            self.mot_coil_current_2nd_molasses.get(),
            self.molasses_xodt_2.general_setter_default_starts[0],
            self.molasses_xodt_2.general_setter_default_starts[1],
            self.molasses_xodt_2.general_setter_default_starts[2],
        )
        # Turn off MOT beams between molasses if there is a gap
        if self.delay_between_molasses.get() > 1e-6:
            self.red_mot.red_beam_controller.all_mot_beams_setter.turn_beams_off(
                ignore_shutters=True
            )

        # Step the 689 stir frequency
        self.blue_3d_mot.mirny_eom_sidebands.set_689_stir_sideband_detuning(
            detuning=self.stir_beam_detuning_molasses_2.get()
        )

        delay(self.delay_between_molasses.get())

        self.red_mot.red_beam_controller.all_mot_beams_setter.turn_beams_on(
            ignore_shutters=True
        )
        self.molasses_xodt_2.do_phase()


class EvapAndFieldRampBase(DipoleTrapWithExperiment):
    """
    Exposes the evaporation and field ramping phase for use in evaporation Mixins
    """

    def build_fragment(self):
        super().build_fragment()

        self.setattr_fragment(
            "bias_and_evap_ramp", XODTWithFieldRamp, enforce_binding_to_defaults=False
        )
        self.bias_and_evap_ramp: XODTWithFieldRamp

    @kernel
    def DMA_initialization_hook_evap_with_field_ramp(self):
        self.bias_and_evap_ramp.precalculate_dma_handle()

    @kernel
    def DMA_initialization_hook(self):
        raise NotImplementedError(
            "All the DMA handle calculations must be combined into one \
                DMA_initialization_hook() method after Mixins are combined"
        )

    @kernel
    def dipole_trap_evaporation_hook_with_field_ramp(self):
        """
        Do the evap and field ramp
        """
        self.bias_and_evap_ramp.do_phase()

    @kernel
    def dipole_trap_evaporation_hook(self):
        # Default hook turns off red beams - good!
        self.dipole_trap_evaporation_hook_default()
        self.dipole_trap_evaporation_hook_with_field_ramp()


class XODTDoubleMolassesPlusFieldRampMixin(
    XODTDoubleMolassesMixin, EvapAndFieldRampBase
):
    """
    Loads atoms into a dipole trap after the narrowband red MOT, implements two
    ramping molasses, then a final evaporation and bias magnetic field ramp phase.

    This is a mixin - see the documentation for :mod:`~.dipole_trap_experiment` for
    details.

    Kernel hooks used (multiple mixins cannot use the same hooks):

    * :meth:`~DMA_initialization_hook`
    * :meth:`~before_start_hook`
    * :meth:`~post_narrowband_hook`
    * :meth:`~dipole_trap_molasses_hook`
    * :meth:`~dipole_trap_evaporation_hook`

    We override this to do nothing since this Mixin is now taking charge of field setting:

    * :meth:`~set_postnarrowband_fields_hook`
    """

    def build_fragment(self):
        super().build_fragment()

        self.bias_and_evap_ramp.daisy_chain_with_previous_phase(
            self.molasses_xodt_2, suservos=suservos_XODT
        )

    @kernel
    def DMA_initialization_hook(self):
        self.DMA_initialization_hook_default()
        self.DMA_initialization_hook_xodt_molasses()
        self.DMA_initialization_hook_evap_with_field_ramp()


class XODTSingleMolassesPlusFieldRampMixin(
    XODTSingleMolassesMixin, EvapAndFieldRampBase
):
    """
    Loads atoms into a dipole trap after the narrowband red MOT, implements a
    ramping molasses, then a final evaporation and bias magnetic field ramp phase.

    This is a mixin - see the documentation for :mod:`~.dipole_trap_experiment` for
    details.

    Kernel hooks used (multiple mixins cannot use the same hooks):

    * :meth:`~DMA_initialization_hook`
    * :meth:`~before_start_hook`
    * :meth:`~post_narrowband_hook`
    * :meth:`~dipole_trap_molasses_hook`
    * :meth:`~dipole_trap_evaporation_hook`

    We override this to do nothing since this Mixin is now taking charge of field setting:

    * :meth:`~set_postnarrowband_fields_hook`
    """

    def build_fragment(self):
        super().build_fragment()

        self.bias_and_evap_ramp.daisy_chain_with_previous_phase(
            self.molasses_xodt_1, suservos=suservos_XODT
        )

    @kernel
    def DMA_initialization_hook(self):
        self.DMA_initialization_hook_default()
        self.DMA_initialization_hook_xodt_molasses()
        self.DMA_initialization_hook_evap_with_field_ramp()
