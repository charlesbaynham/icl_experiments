import logging

from artiq.experiment import kernel
from ndscan.experiment.parameters import FloatParam
from ndscan.experiment.parameters import FloatParamHandle

from repository.lib import constants
from repository.lib.experiment_templates.dipole_trap_experiment import (
    DipoleTrapWithExperiment,
)
from repository.lib.fragments.dipole_trap.dipole_trap_phases import MOTInSingleXODT

logger = logging.getLogger(__name__)


class LoadSingleXODTMixin(DipoleTrapWithExperiment):
    """
    Loads atoms in a single XODT after the narrowband red MOT

    Ramps the dipole trap beams on at the start of a stage of ramping MOT beams.

    Kernel hooks used (multiple mixins cannot use the same hooks):

    * :meth:`~DMA_initialization_hook`
    * :meth:`~post_narrowband_hook`
    * :meth:`~dipole_trap_loading_hook`

    We also override this hook to do nothing since this Mixin is now taking
    charge of field setting:

    * :meth:`~set_postnarrowband_fields_hook`
    """

    def build_fragment(self):
        super().build_fragment()

        self.setattr_fragment("mot_xodt", MOTInSingleXODT)
        self.mot_xodt: MOTInSingleXODT

        # Remove unused parameters
        self.override_param("spectroscopy_field_gradient", 0)

        self.setattr_param(
            "stir_beam_detuning_mot_xodt",
            FloatParam,
            "Detuning of the 689 stir beam during xodt loading",
            default=constants.XODT_SINGLE_LOADING_STIR_DETUNING,
            unit="kHz",
            min=-2e6,
            max=2e6,
        )
        self.stir_beam_detuning_mot_xodt: FloatParamHandle

        self.mot_xodt.bind_suservo_setpoint_params_to_default_beam_setter(
            [
                self.red_mot.red_beam_controller.all_beam_default_setter,
                self.dipole_beam_controller.all_beam_default_setter,
            ]
        )

        self.mot_xodt.bind_ad9910_frequency_params(
            [self.red_mot.injection_aom_static_frequency]
        )

    @kernel
    def DMA_initialization_hook(self):
        self.DMA_initialization_hook_default()
        self.DMA_initialization_hook_single_xodt_mot()

    @kernel
    def DMA_initialization_hook_single_xodt_mot(self):
        """
        Preload phases' handles. These have to be grouped together, instead of
        handled in separate subfragment setups, otherwise only the last-compiled
        dma handle is valid.
        """
        self.mot_xodt.precalculate_dma_handle()

    @kernel
    def post_narrowband_hook(self):
        pass

    @kernel
    def set_postnarrowband_fields_hook(self):
        pass

    @kernel
    def dipole_trap_loading_hook(self):
        self.dipole_trap_loading_hook_single_xodt_mot()

    @kernel
    def dipole_trap_loading_hook_single_xodt_mot(self):
        """
        Turn the dipole beams on and do the xodt loading ramping phase
        """
        self.constant_dipole_traps_setter.turn_on_all()

        self.red_mot.red_beam_controller.all_mot_beams_setter.turn_beams_on(  # FIXME Get rid of this and make sure it works
            ignore_shutters=True
        )

        # Step the 689 stir frequency
        self.blue_3d_mot.mirny_eom_sidebands.set_689_stir_sideband_detuning(
            detuning=self.stir_beam_detuning_mot_xodt.get()
        )

        self.mot_xodt.do_phase()


class LoadXXODT(DipoleTrapWithExperiment):
    """
    Loads atoms into a double crossed dipole trap after the narrowband red MOT


    Kernel hooks used (multiple mixins cannot use the same hooks):

    * :meth:`~DMA_initialization_hook`
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

        self.setattr_fragment(
            "transparency_suservo",
            LibSetSUServoStatic,
            constants.SUSERVOED_BEAMS["blue_transparency_beam"].suservo_device,
        )
        self.transparency_suservo: LibSetSUServoStatic

        self.setattr_fragment(
            "transparency_setter",
            make_set_beams_to_default(
                suservo_beam_infos=[constants.SUSERVOED_BEAMS["blue_transparency_beam"]]
            ),
        )
        self.transparency_setter: SetBeamsToDefaults

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

        # FIXME: this is using the high intensity setter, and maybe setting the wrong pgia?
        self.molasses_xodt_1.bind_suservo_setpoint_params_to_default_beam_setter(
            [
                self.red_mot.red_beam_controller.all_beam_default_setter,
                self.dipole_beam_controller.all_beam_default_setter,
                self.transparency_setter,
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
    def post_narrowband_hook(self):
        pass

    @kernel
    def set_postnarrowband_fields_hook(self):
        self.set_postnarrowband_fields_hook_singlemolasses()

    @kernel
    def set_postnarrowband_fields_hook_singlemolasses(self):
        pass

    @kernel
    def dipole_trap_molasses_hook(self):
        self.set_fields_xodt_molasses()
        self.dipole_trap_molasses_hook_first_xodt_molasses()

    @kernel
    def set_fields_xodt_molasses(self):
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
    def dipole_trap_molasses_hook_first_xodt_molasses(self):
        """
        Do the first molasses ramping phase
        """

        # turn on red beams and transparency beam
        red_suservos = (
            self.red_mot.red_beam_controller.all_beam_default_setter.suservo_setters_and_info
        )
        for i in range(len(red_suservos)):
            red_suservos[i].setter.set_setpoint(0.0)
        self.red_mot.red_beam_controller.all_mot_beams_setter.turn_beams_on(
            ignore_shutters=True
        )
        self.transparency_setter.turn_on_all()

        # Step the 689 stir frequency
        self.blue_3d_mot.mirny_eom_sidebands.set_689_stir_sideband_detuning(
            detuning=self.stir_beam_detuning_molasses_1.get()
        )

        self.molasses_xodt_1.do_phase()

        # turn off transparency beam
        self.transparency_suservo.set_channel_state(
            rf_switch_state=False, enable_iir=False
        )

        self.red_mot.red_beam_controller.all_mot_beams_setter.turn_beams_off(
            ignore_shutters=True
        )
