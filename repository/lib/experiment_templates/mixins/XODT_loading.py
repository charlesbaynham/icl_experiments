import logging

from artiq.language import delay
from artiq.language import kernel
from ndscan.experiment.parameters import FloatParam
from ndscan.experiment.parameters import FloatParamHandle
from pyaion.fragments.default_beam_setter import SetBeamsToDefaults
from pyaion.fragments.default_beam_setter import make_set_beams_to_default

from repository.lib import constants
from repository.lib.experiment_templates.dipole_trap_experiment import (
    DipoleTrapWithExperimentBase,
)
from repository.lib.fragments.beams.toggling_beam_setter import ToggleListOfBeams
from repository.lib.fragments.beams.toggling_beam_setter import (
    make_toggle_list_of_beams,
)
from repository.lib.fragments.dipole_trap.dipole_trap_phases import MOTInBottomXODT
from repository.lib.fragments.dipole_trap.dipole_trap_phases import MOTInSingleXODT
from repository.lib.fragments.painted_pulse import (
    GravityAndDiffractionCompensatedQuadraticShapedPulse,
)

logger = logging.getLogger(__name__)


class LoadSingleXODTMixin(DipoleTrapWithExperimentBase):
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

        self.setattr_fragment("mot_in_xodt", MOTInSingleXODT)
        self.mot_in_xodt: MOTInSingleXODT

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

        self.mot_in_xodt.bind_suservo_setpoint_params_to_default_beam_setter(
            [
                self.red_mot.red_beam_controller.all_beam_default_setter,
                self.dipole_beam_controller.all_beam_default_setter,
            ]
        )

        self.mot_in_xodt.bind_ad9910_frequency_params(
            [self.red_mot.injection_aom_static_frequency]
        )

    @kernel
    def DMA_initialization_hook(self):
        self.DMA_initialization_hook_default()
        self.DMA_initialization_hook_loading_xodt_mot()

    @kernel
    def DMA_initialization_hook_loading_xodt_mot(self):
        """
        Preload phases' handles. These have to be grouped together, instead of
        handled in separate subfragment setups, otherwise only the last-compiled
        dma handle is valid.
        """
        self.mot_in_xodt.precalculate_dma_handle()

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
        self.dipole_beam_controller.turn_on_dipole_beams()

        # Step the 689 stir frequency
        self.blue_3d_mot.mirny_eom_sidebands.set_689_stir_sideband_detuning(
            detuning=self.stir_beam_detuning_mot_xodt.get()
        )

        self.mot_in_xodt.do_phase()


class LoadSingleXODTWithPainterMixin(LoadSingleXODTMixin):
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

        self.setattr_fragment(
            "painter_driver_loading",
            GravityAndDiffractionCompensatedQuadraticShapedPulse,
            ad9910_name=constants.PAINTING_URUKUL_CHANNEL,
            automatic_trigger=True,
            ram_offset=0,
        )
        self.painter_driver_loading: (
            GravityAndDiffractionCompensatedQuadraticShapedPulse
        )

    @kernel
    def post_sequence_cleanup_hook_loading(self):
        self.dipole_beam_controller.turn_off_painter_suservo()
        self.painter_driver_loading.stop_output()

    @kernel
    def post_sequence_cleanup_hook(self):
        self.post_sequence_cleanup_hook_base()
        self.post_sequence_cleanup_hook_loading()

    @kernel
    def dipole_trap_loading_hook(self):
        self.dipole_beam_controller.turn_on_painter_suservo()
        self.dipole_trap_loading_hook_single_xodt_mot()


class LoadXXODTMixin(LoadSingleXODTMixin):
    """
    Loads atoms into a double crossed dipole trap after the narrowband red MOT

    Kernel hooks used (multiple mixins cannot use the same hooks):

    * :meth:`~DMA_initialization_hook`
    * :meth:`~post_narrowband_hook`
    * :meth:`~dipole_trap_loading_hook`

    We also override this hook to do nothing since this Mixin is now taking charge
    of field setting:

    * :meth:`~set_postnarrowband_fields_hook`
    """

    def build_fragment(self):
        super().build_fragment()

        self.setattr_fragment("mot_in_second_xodt", MOTInBottomXODT)
        self.mot_in_second_xodt: MOTInBottomXODT

        # Parameters for the bias field jump
        for axis, default_current in zip(
            "xyz",
            [
                constants.RED_NARROWBAND_BIAS_FIELD_BACKWARD_X,
                constants.RED_NARROWBAND_BIAS_FIELD_BACKWARD_Y,
                constants.RED_NARROWBAND_BIAS_FIELD_BACKWARD_Z,
            ],
        ):
            self.setattr_param_like(
                f"field_bias_second_xodt_{axis}",
                self.red_mot,
                f"narrowband_bias_{axis}",
                description=f"Bias field during second XODT loading {axis}",
                default=default_current,
            )

        self.setattr_param_like(
            "field_gradient_second_xodt",
            self.blue_3d_mot,
            "chamber_2_field_gradient",
            description="Field gradient during second XODT loading",
            default=constants.RED_NARROWBAND_GRADIENT_FIELD_BACKWARD,
        )

        self.field_bias_second_xodt_x: FloatParamHandle
        self.field_bias_second_xodt_y: FloatParamHandle
        self.field_bias_second_xodt_z: FloatParamHandle
        self.field_gradient_second_xodt: FloatParamHandle

        self.setattr_param(
            "delay_before_second_xodt",
            FloatParam,
            "Time to hold in top dipole trap before turning on light for second",
            default=constants.XXODT_LOWER_LOADING_WAIT_BEFORE,
            unit="ms",
        )
        self.delay_before_second_xodt: FloatParamHandle

        self.setattr_param(
            "stir_beam_detuning_mot_second_xodt",
            FloatParam,
            "Detuning of the 689 stir beam during second xodt loading",
            default=constants.XXODT_LOWER_LOADING_689_STIR_DETUNING,
            unit="kHz",
            min=-2e6,
            max=2e6,
        )
        self.stir_beam_detuning_mot_second_xodt: FloatParamHandle

        # Bind the nominal setpoints and frequencies for this stage only - we want to be able to jump discontinuously
        self.mot_in_second_xodt.daisy_chain_with_previous_phase(self.mot_in_xodt)

    @kernel
    def DMA_initialization_hook_loading_xodt_mot(self):
        """
        Override the DMA calculation for the single XODT to save the user having to write two hooks
        """
        self.mot_in_xodt.precalculate_dma_handle()
        self.mot_in_second_xodt.precalculate_dma_handle()

    @kernel
    def dipole_trap_loading_hook(self):
        self.dipole_trap_loading_hook_single_xodt_mot()
        self.dipole_trap_loading_hook_second_xodt_mot()

    @kernel
    def dipole_trap_loading_hook_second_xodt_mot(self):

        # Turn the red beams off if there's time
        if self.delay_before_second_xodt.get() > 1e-6:
            self.red_mot.red_beam_controller.all_mot_beams_setter.turn_beams_off(
                ignore_shutters=True
            )

        # Step the 689 stir frequency
        self.blue_3d_mot.mirny_eom_sidebands.set_689_stir_sideband_detuning(
            detuning=self.stir_beam_detuning_mot_second_xodt.get()
        )

        # Step the field
        self.red_mot.chamber_2_field_setter.set_all_fields(
            current_mot=self.field_gradient_second_xodt.get(),
            current_x=self.field_bias_second_xodt_x.get(),
            current_y=self.field_bias_second_xodt_y.get(),
            current_z=self.field_bias_second_xodt_z.get(),
        )

        delay(self.delay_before_second_xodt.get())

        # Beams on and load into the second XODT
        if self.delay_before_second_xodt.get() > 1e-6:
            self.red_mot.red_beam_controller.all_mot_beams_setter.turn_beams_on(
                ignore_shutters=True
            )

        self.mot_in_second_xodt.do_phase()

        # Leave the red beams on. They will be either used for spin pol or
        # turned off by the evaporation stage.


class LoadXXODTWithTransparencyBeamMixin(LoadXXODTMixin):
    """
    Loads atoms into a double crossed dipole trap after the narrowband red MOT
    with a transparency beam protecting the top trap during the second XODT

    Kernel hooks used (multiple mixins cannot use the same hooks):

    * :meth:`~DMA_initialization_hook`
    * :meth:`~post_narrowband_hook`
    * :meth:`~dipole_trap_loading_hook`

    We also override this hook to do nothing since this Mixin is now taking charge
    of field setting:

    * :meth:`~set_postnarrowband_fields_hook`
    """

    def build_fragment(self):
        super().build_fragment()

        # %% Fragments

        self.setattr_fragment(
            "transparency_toggler",
            make_toggle_list_of_beams(
                [constants.SUSERVOED_BEAMS["blue_transparency_beam"]],
            ),
        )
        self.transparency_toggler: ToggleListOfBeams

        self.setattr_fragment(
            "transparency_setter",
            make_set_beams_to_default(
                suservo_beam_infos=[
                    constants.SUSERVOED_BEAMS["blue_transparency_beam"]
                ],
                use_automatic_setup=True,
                use_automatic_turnon=False,
            ),
        )
        self.transparency_setter: SetBeamsToDefaults

    @kernel
    def dipole_trap_loading_hook(self):
        self.dipole_trap_loading_hook_single_xodt_mot()

        # Repump the atoms throughout loading to avoid shelving into the
        # metastable states
        self.blue_3d_mot.turn_on_repumpers()
        self.transparency_toggler.turn_on_beams()

        self.dipole_trap_loading_hook_second_xodt_mot()

        # Turn off the transparency beam after the second XODT. The red beams
        # are left on by default so they can be used for spin pol - if we're not
        # doing spin pol, the default evaporation stage will turn them off. Why
        # do we use the "evaporation stage" to turn off our red beams? Legacy code,
        # innit.
        self.transparency_toggler.turn_off_beams()
        self.blue_3d_mot.turn_off_repumpers()
