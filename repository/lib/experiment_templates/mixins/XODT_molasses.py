import logging

from artiq.language import delay
from artiq.language import delay_mu
from artiq.language import kernel
from ndscan.experiment.parameters import FloatParam
from ndscan.experiment.parameters import FloatParamHandle
from pyaion.fragments.default_beam_setter import SetBeamsToDefaults
from pyaion.fragments.default_beam_setter import make_set_beams_to_default
from pyaion.fragments.suservo import LibSetSUServoStatic

from repository.lib import constants
from repository.lib.experiment_templates.dipole_trap_experiment import (
    DipoleTrapWithExperimentBase,
)
from repository.lib.experiment_templates.mixins.evaporation_mixin import (
    EvapAndFieldRampBase,
)
from repository.lib.fragments.beams.toggling_beam_setter import ToggleListOfBeams
from repository.lib.fragments.beams.toggling_beam_setter import (
    make_toggle_list_of_beams,
)
from repository.lib.fragments.dipole_trap.dipole_trap_phases import SUSERVOS_XODT
from repository.lib.fragments.dipole_trap.dipole_trap_phases import MolassesDipoleRamp
from repository.lib.fragments.dipole_trap.dipole_trap_phases import MolassesInXODT
from repository.lib.fragments.dipole_trap.dipole_trap_phases import MolassesRetroed

MOLASSES_SUSERVO_INFOS = [constants.SUSERVOED_BEAMS["red_molasses"]]

logger = logging.getLogger(__name__)

TRANSPARENCY_AOM_FREQ = constants.SUSERVOED_BEAMS["blue_transparency_beam"].frequency

SUSERVOS_XODT = [
    "suservo_aom_1064_delivery",
    "suservo_aom_down_813",
]

SUSERVO_PAINTER = ["suservo_aom_1064_painted_delivery"]

SUSERVO_UP_813 = ["suservo_aom_up_813"]

SUSERVO_IN_DIPOLE_RAMP = [
    "suservo_aom_1064_delivery",
    "suservo_aom_down_813",
    "suservo_aom_1064_painted_delivery",
    "suservo_aom_up_813",
]


class XODTSingleMolassesMixin(DipoleTrapWithExperimentBase):
    """
    Loads atoms into a dipole trap after the narrowband red MOT, and implements a
    single stage of ramping molasses (or MOT) with ramping bias magnetic field.

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

        self.setattr_fragment(
            "up_813_setter",
            make_set_beams_to_default(
                suservo_beam_infos=[constants.SUSERVOED_BEAMS["up_813"]]
            ),
        )
        self.up_813_setter: SetBeamsToDefaults

        self.setattr_param_rebind(
            "red_narrowband_mot_689_up_start",
            self.red_mot.narrow_red_compression_phase,
            original_name="setpoint_multiple_start_suservo_aom_singlepass_689_up",
            default=constants.RED_COMPRESSION_MOT_UP_BEAM_SETPOINT_FOR_MOLASSES,
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
            default=constants.XODT_MOLASSES_689_STIR_DETUNING,
            unit="kHz",
            min=-2e6,
            max=2e6,
        )
        self.stir_beam_detuning_molasses_1: FloatParamHandle

        self.molasses_xodt_1.bind_suservo_setpoint_params_to_default_beam_setter(
            [
                self.red_mot.red_beam_controller.all_beam_default_setter,
                self.dipole_beam_controller.all_beam_default_setter,
                self.transparency_setter,
                self.up_813_setter,
            ]
        )

        self.molasses_xodt_1.bind_ad9910_frequency_params(
            [self.red_mot.injection_aom_static_frequency]
        )

    def get_always_shown_params(self):
        # Expose the clock base frequency for convenience
        param_handles = super().get_always_shown_params()
        param_handles.remove(self.red_narrowband_mot_689_up_start)
        param_handles.remove(self.delay_before_molasses)
        param_handles.remove(self.mot_coil_current_first_molasses)
        return param_handles

    @kernel
    def DMA_initialization_hook(self):
        self.DMA_initialization_hook_redmot_default()
        self.DMA_initialization_hook_dipole_trap_default()
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
        self.blue_3d_mot.repump_beam_setter.turn_beams_on()
        # Step the 689 stir frequency
        self.blue_3d_mot.mirny_eom_sidebands.set_689_stir_sideband_detuning(
            detuning=self.stir_beam_detuning_molasses_1.get()
        )

        self.molasses_xodt_1.do_phase()

        # turn off transparency beam
        self.transparency_suservo.set_channel_state(
            rf_switch_state=False, enable_iir=False
        )
        self.blue_3d_mot.repump_beam_setter.turn_beams_off(ignore_shutters=True)

        self.red_mot.red_beam_controller.all_mot_beams_setter.turn_beams_off(
            ignore_shutters=True
        )


class XODTSingleMolassesPlusDipoleRampMixin(XODTSingleMolassesMixin):
    """
    Loads atoms into a dipole trap after the narrowband red MOT, and implements a
    ramping molasses followed by a ramp of the dipole trap beams.


    This is a mixin - see the documentation for :mod:`~.dipole_trap_experiment` for
    details.

    Kernel hooks used (multiple mixins cannot use the same hooks):

    * :meth:`~DMA_initialization_hook`
    * :meth:`~post_narrowband_hook`
    * :meth:`~dipole_trap_molasses_hook`

    We override this to do nothing since this Mixin is now taking charge of field setting:

    * :meth:`~set_postnarrowband_fields_hook`
    """

    def build_fragment(self):
        super().build_fragment()

        self.setattr_fragment(
            "cool_molasses", MolassesDipoleRamp, enforce_binding_to_defaults=False
        )
        self.cool_molasses: MolassesDipoleRamp

        # self.cool_molasses.bind_suservo_setpoint_params_to_default_beam_setter(
        #     [self.dipole_beam_controller.all_beam_default_setter]
        # )

        self.cool_molasses.daisy_chain_with_previous_phase(
            self.molasses_xodt_1, SUSERVO_IN_DIPOLE_RAMP
        )

    @kernel
    def DMA_initialization_hook(self):
        self.DMA_initialization_hook_redmot_default()
        self.DMA_initialization_hook_dipole_trap_default()
        self.DMA_initialization_hook_xodt_molasses()

    @kernel
    def DMA_initialization_hook_xodt_molasses(self):
        """
        Preload phases' handles. These have to be grouped together, instead of
        handled in separate subfragment setups, otherwise only the last-compiled
        dma handle is valid.
        """
        self.molasses_xodt_1.precalculate_dma_handle()
        self.cool_molasses.precalculate_dma_handle()

    @kernel
    def dipole_trap_molasses_hook(self):
        self.set_fields_xodt_molasses()
        self.dipole_trap_molasses_hook_first_xodt_molasses()
        # self.dipole_beam_controller.()
        self.dipole_trap_molasses_hook_cool_molasses()

    @kernel
    def dipole_trap_molasses_hook_cool_molasses(self):
        """
        Adiabatically cool after the molasses
        """
        self.cool_molasses.do_phase()


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
    * :meth:`~post_narrowband_hook`
    * :meth:`~dipole_trap_molasses_hook`
    * :meth:`~dipole_trap_evaporation_hook`

    We override this to do nothing since this Mixin is now taking charge of field setting:

    * :meth:`~set_postnarrowband_fields_hook`
    """

    def _bind_evap_ramp_suservo_params(self):
        pass  # daisy_chain_with_previous_phase below handles the binding instead

    def build_fragment(self):
        super().build_fragment()

        self.ramp_during_evap_phase.daisy_chain_with_previous_phase(
            self.molasses_xodt_1, suservos=SUSERVOS_XODT
        )

    @kernel
    def DMA_initialization_hook(self):
        self.DMA_initialization_hook_redmot_default()
        self.DMA_initialization_hook_dipole_trap_default()
        self.DMA_initialization_hook_xodt_molasses()
        self.DMA_initialization_hook_evap_with_field_ramp()


class ClearOut689Mixin(DipoleTrapWithExperimentBase):
    """
    Pulse 689 nm beam to clear out atoms after molasses

    This is a mixin - see the documentation for :mod:`~.dipole_trap_experiment` for
    details.

    Kernel hooks used (multiple mixins cannot use the same hooks):

    * :meth:`~do_clearout_pulse_hook`

    """

    def build_fragment(self):
        # We assume that the up beam has already been configured by the MOT
        # sequence, but that we must control the amplitude
        self.setattr_fragment(
            "up_beam_suservo",
            LibSetSUServoStatic,
            constants.SUSERVOED_BEAMS["red_up"].suservo_device,
        )
        self.up_beam_suservo: LibSetSUServoStatic

        self.setattr_fragment(
            "transparency_toggler",
            make_toggle_list_of_beams(
                [constants.SUSERVOED_BEAMS["blue_transparency_beam"]],
            ),
        )
        self.transparency_toggler: ToggleListOfBeams

        self.setattr_fragment(
            "transparency_suservo_clearout",
            LibSetSUServoStatic,
            constants.SUSERVOED_BEAMS["blue_transparency_beam"].suservo_device,
        )
        self.transparency_suservo_clearout: LibSetSUServoStatic

        # self.setattr_fragment(
        #     "transparency_setter_clearout",
        #     make_set_beams_to_default(
        #         suservo_beam_infos=[constants.SUSERVOED_BEAMS["blue_transparency_beam"]]
        #     ),
        # )
        # self.transparency_setter_clearout: SetBeamsToDefaults

        self.setattr_param(
            "clearout_pulse_time",
            FloatParam,
            "Time to pulse the 689 nm beam to clear out atoms",
            default=0.0,
            unit="ms",
        )
        self.clearout_pulse_time: FloatParamHandle

        self.setattr_param(
            "clearout_pulse_aom_amplitude",
            FloatParam,
            "Amplitude of delivery AOM during clearout pulse. SUServoing is disabled",
            default=1.0,
            min=0.0,
            max=1.0,
        )
        self.clearout_pulse_aom_amplitude: FloatParamHandle

        self.setattr_param(
            "setpoint_487_during_clearout",
            FloatParam,
            "Setpoint for the 487 during the 689 clearout pulse",
            default=0.2,
            unit="V",
        )
        self.setpoint_487_during_clearout: FloatParamHandle

        super().build_fragment()

    @kernel
    def do_clearout_pulse_hook(self):
        self.transparency_suservo_clearout.set_setpoint(
            self.setpoint_487_during_clearout.get()
        )
        self.transparency_suservo_clearout.set_suservo(
            amplitude=1.0,
            freq=80e6,
            rf_switch_state=True,
            enable_iir=True,
            setpoint_v=self.setpoint_487_during_clearout.get(),
            attenuation=0.0,
        )
        delay_mu(8)
        self.up_beam_suservo.set_pgia_gain_mu(0)
        delay_mu(8)
        self.up_beam_suservo.suservo_channel.set_y(
            profile=self.up_beam_suservo.suservo_profile,
            y=self.clearout_pulse_aom_amplitude.get(),
        )
        delay_mu(8)
        self.up_beam_suservo.set_channel_state(rf_switch_state=True, enable_iir=False)
        delay(self.clearout_pulse_time.get())
        self.up_beam_suservo.set_channel_state(rf_switch_state=False, enable_iir=False)

        delay_mu(8)
        # turn off transparency suservo
        # self.transparency_suservo_clearout.set_channel_state(
        #     rf_switch_state=False, enable_iir=False
        # )
        self.transparency_suservo_clearout.set_channel_state(
            rf_switch_state=False, enable_iir=False
        )


class MolassesRetroedBeamMixin(DipoleTrapWithExperimentBase):
    """
    Mixin for the molasses with the retroreflected molasses beam

    This is a mixin - see the documentation for :mod:`~.dipole_trap_experiment` for
    details.

    Kernel hooks used (multiple mixins cannot use the same hooks):

    * :meth:`~DMA_initialization_hook`
    * :meth:`~dipole_trap_molasses_hook`

    """

    def build_fragment(self):
        super().build_fragment()

        self.setattr_fragment(
            "molasses_xodt_retroed",
            MolassesRetroed,
        )
        self.molasses_xodt_retroed: MolassesRetroed

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

        self.setattr_fragment(
            "molasses_suservo",
            LibSetSUServoStatic,
            MOLASSES_SUSERVO_INFOS[0].suservo_device,
        )
        self.molasses_suservo: LibSetSUServoStatic

        # Setup of defaults for all molasses beam
        self.setattr_fragment(
            "molasses_beam_default_setter",
            make_set_beams_to_default(
                suservo_beam_infos=MOLASSES_SUSERVO_INFOS,
                name="MolassesBeamSettings",
                use_automatic_setup=True,  # Automatically configure the DDSs but do not turn the beams on
                use_automatic_turnon=False,
            ),
        )
        self.molasses_beam_default_setter: SetBeamsToDefaults

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
            "bias_current_multiple_first_molasses",
            FloatParam,
            "Bias field amplitude during first molasses",
            default=0.1,
        )
        self.bias_current_multiple_first_molasses: FloatParamHandle

        self.molasses_xodt_retroed.bind_suservo_setpoint_params_to_default_beam_setter(
            [
                self.dipole_beam_controller.all_beam_default_setter,
                self.molasses_beam_default_setter,
                self.transparency_setter,
            ]
        )

        self.molasses_xodt_retroed.bind_ad9910_frequency_params(
            [self.red_mot.red_beam_controller.spinpol_aom_static_frequency]
        )

    @kernel
    def DMA_initialization_hook_xodt_molasses(self):
        """
        Preload phases' handles. These have to be grouped together, instead of
        handled in separate subfragment setups, otherwise only the last-compiled
        dma handle is valid.
        """
        self.molasses_xodt_retroed.precalculate_dma_handle()

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
        comp_field = [
            constants.FIELD_COMP_X,
            constants.FIELD_COMP_Y,
            constants.FIELD_COMP_Z,
        ]
        molasses_field = [
            0.3983,
            0.0653,
            0.2681,
        ]
        multiple_bias = self.bias_current_multiple_first_molasses.get()
        self.red_mot.chamber_2_field_setter.set_all_fields(
            self.mot_coil_current_first_molasses.get(),
            multiple_bias * molasses_field[0] + comp_field[0],
            multiple_bias * molasses_field[1] + comp_field[1],
            multiple_bias * molasses_field[2] + comp_field[2],
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

        # turn on molasses beam and transparency beam

        self.molasses_beam_default_setter.turn_on_all()
        self.transparency_setter.turn_on_all()

        self.molasses_xodt_retroed.do_phase()

        # turn off transparency beam
        self.transparency_suservo.set_channel_state(
            rf_switch_state=False, enable_iir=False
        )

        self.molasses_suservo.set_channel_state(rf_switch_state=False, enable_iir=False)


class XODTRetroedMolassesPlusDipoleRampMixin(MolassesRetroedBeamMixin):
    """
    Loads atoms into a dipole trap after the narrowband red MOT, and implements a
    ramping molasses followed by a ramp of the dipole trap beams.


    This is a mixin - see the documentation for :mod:`~.dipole_trap_experiment` for
    details.

    Kernel hooks used (multiple mixins cannot use the same hooks):

    * :meth:`~DMA_initialization_hook`
    * :meth:`~post_narrowband_hook`
    * :meth:`~dipole_trap_molasses_hook`

    We override this to do nothing since this Mixin is now taking charge of field setting:

    * :meth:`~set_postnarrowband_fields_hook`
    """

    def build_fragment(self):
        super().build_fragment()

        self.setattr_fragment(
            "cool_molasses", MolassesDipoleRamp, enforce_binding_to_defaults=False
        )
        self.cool_molasses: MolassesDipoleRamp

        self.cool_molasses.bind_suservo_setpoint_params_to_default_beam_setter(
            [self.dipole_beam_controller.all_beam_default_setter]
        )

        # self.cool_molasses.daisy_chain_with_previous_phase(
        #     self.molasses_xodt_1, suservos=suservos_XODT
        # )

    @kernel
    def DMA_initialization_hook(self):
        self.DMA_initialization_hook_redmot_default()
        self.DMA_initialization_hook_dipole_trap_default()
        self.DMA_initialization_hook_xodt_molasses()

    @kernel
    def DMA_initialization_hook_xodt_molasses(self):
        """
        Preload phases' handles. These have to be grouped together, instead of
        handled in separate subfragment setups, otherwise only the last-compiled
        dma handle is valid.
        """
        self.molasses_xodt_retroed.precalculate_dma_handle()
        self.cool_molasses.precalculate_dma_handle()

    @kernel
    def dipole_trap_molasses_hook(self):
        self.set_fields_xodt_molasses()
        self.dipole_trap_molasses_hook_first_xodt_molasses()
        # step fields
        multiple_bias_step = 2
        self.red_mot.chamber_2_field_setter.set_all_fields(
            self.mot_coil_current_first_molasses.get(),
            constants.FIELD_COMP_X + multiple_bias_step * 0.3983,
            constants.FIELD_COMP_Y + multiple_bias_step * 0.0653,
            constants.FIELD_COMP_Z + multiple_bias_step * 0.2681,
        )
        self.dipole_trap_molasses_hook_cool_molasses()

    @kernel
    def dipole_trap_molasses_hook_cool_molasses(self):
        """
        Adiabatically cool after the molasses
        """
        self.cool_molasses.do_phase()
