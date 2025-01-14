import logging

from artiq.coredevice.core import Core
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
from repository.lib.fragments.checkpoint_fragment import RedMOTCheckpoints
from repository.lib.fragments.dipole_trap.dipole_trap_beam_controller import (
    DipoleBeamController,
)
from repository.lib.fragments.dipole_trap.dipole_trap_phases import MolassesInXODT
from repository.lib.fragments.dipole_trap.dipole_trap_phases import XODTWithFieldRamp
from repository.lib.fragments.dipole_trap.dipole_trap_phases import suservos_XODT
from repository.lib.fragments.red_mot import RedMOTThreePhaseFrag

logger = logging.getLogger(__name__)


class XODTSingleMolassesMixin(DipoleTrapWithExperiment):
    """
    Loads atoms into a dipole trap after the narrowband red MOT, and implements a
    single stage of ramping molasses (or MOT) with ramping bias magnetic field.

    Kernel hooks used (multiple mixins cannot use the same hooks):

    * :meth:`~dipole_trap_molasses_hook`
    * :meth:`~set_postnarrowband_fields_hook`
    """

    def build_fragment(self):
        super().build_fragment()

        # Remove unused parameters
        self.override_param("spectroscopy_field_gradient", 0)

        self.setattr_fragment("molasses_xodt_1", MolassesInXODT)
        self.molasses_xodt_1: MolassesInXODT

        class XODTSingleMolassesFrag(RedMOTCheckpoints):
            def build_fragment(
                self,
                red_mot: RedMOTThreePhaseFrag,
                dipole_beam_controller: DipoleBeamController,
                molasses_xodt_1: MolassesInXODT,
            ):
                self.kernel_invariants = getattr(self, "kernel_invariants", set())

                self.red_mot = red_mot
                self.kernel_invariants.add("red_mot")

                self.dipole_beam_controller = dipole_beam_controller
                self.kernel_invariants.add("dipole_beam_controller")

                self.molasses_xodt_1 = molasses_xodt_1
                self.kernel_invariants.add("molasses_xodt_1")

                self.setattr_device("core")
                self.core: Core

                # Expose the bias field for moving the MOT to the right place
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
            def DMA_initialization_checkpoint(self):
                self.DMA_initialization_checkpoint_subfragments()
                self.molasses_xodt_1.precalculate_dma_handle()

            @kernel
            def device_setup(self):
                """
                Before the blue MOT, turn on the crossed dipole trap beams and
                set setpoints to same as the start of the xodt molasses ramp.
                """
                self.device_setup_subfragments()

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
            def post_narrowband_checkpoint(self):
                """
                The default post_narrowband_hook turns off the beams immediately
                before this checkpoint.

                Here, we also set coil currents and then wait for the configured
                time before starting the molasses (which turns the beams back on
                again)
                """
                self.post_narrowband_checkpoint_subfragments()

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

        self.setattr_fragment(
            "xodt_single_molasses",
            XODTSingleMolassesFrag,
            red_mot=self.red_mot,
            dipole_beam_controller=self.dipole_beam_controller,
            molasses_xodt_1=self.molasses_xodt_1,
        )
        self.xodt_single_molasses: XODTSingleMolassesFrag

    @kernel
    def set_postnarrowband_fields_hook(self):
        self.set_postnarrowband_fields_hook_singlemollasses()

    @kernel
    def set_postnarrowband_fields_hook_singlemollasses(self):
        pass

    @kernel
    def dipole_trap_molasses_hook(self):
        """
        Do the first molasses ramping phase
        """
        self.red_mot.red_beam_controller.all_mot_beams_setter.turn_beams_on(
            ignore_shutters=True
        )

        # Step the 689 stir frequency
        self.blue_3d_mot.mirny_eom_sidebands.set_689_stir_sideband_detuning(
            detuning=self.xodt_single_molasses.stir_beam_detuning_molasses_1.get()
        )

        self.xodt_single_molasses.molasses_xodt_1.do_phase()


class XODTSingleMolassesPlusFieldRampMixin(XODTSingleMolassesMixin):
    """
    Loads atoms into a dipole trap after the narrowband red MOT, implements a
    ramping molasses, then a final evaporation and bias magnetic field ramp phase.

    This is a mixin - see the documentation for :mod:`~.dipole_trap_experiment` for
    details.

    Kernel hooks used (multiple mixins cannot use the same hooks):

    * :meth:`~set_postnarrowband_fields_hook`
    * :meth:`~dipole_trap_molasses_hook`
    * :meth:`~dipole_trap_evaporation_hook`
    """

    def build_fragment(self):
        super().build_fragment()

        self.setattr_fragment(
            "bias_and_evap_ramp", XODTWithFieldRamp, enforce_binding_to_defaults=False
        )
        self.bias_and_evap_ramp: XODTWithFieldRamp

        self.bias_and_evap_ramp.daisy_chain_with_previous_phase(
            self.molasses_xodt_1, suservos=suservos_XODT
        )

        # Make a fragment to initialise DMA for the phase
        # TODO: Consider converting all our phases to checkpoint frags so we can automatically initialise DMA
        class _DMAFrag(RedMOTCheckpoints):
            def build_fragment(self, bias_and_evap_ramp):
                self.bias_and_evap_ramp: XODTWithFieldRamp = bias_and_evap_ramp

            @kernel
            def DMA_initialization_checkpoint(self):
                self.DMA_initialization_checkpoint_subfragments()

                self.bias_and_evap_ramp.precalculate_dma_handle()

        self.setattr_fragment("_DMAFrag", _DMAFrag, self.bias_and_evap_ramp)

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
