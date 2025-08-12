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
    DipoleTrapWithExperiment,
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
from repository.lib.fragments.dipole_trap.dipole_trap_phases import MolassesInXODT_2

logger = logging.getLogger(__name__)

TRANSPARENCY_AOM_FREQ = constants.SUSERVOED_BEAMS["blue_transparency_beam"].frequency


class XODTSingleMolassesMixin(DipoleTrapWithExperiment):
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

        self.cool_molasses.bind_suservo_setpoint_params_to_default_beam_setter(
            [self.dipole_beam_controller.all_beam_default_setter]
        )

        # self.cool_molasses.daisy_chain_with_previous_phase(
        #     self.molasses_xodt_1, suservos=suservos_XODT
        # )

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
        self.cool_molasses.precalculate_dma_handle()

    @kernel
    def dipole_trap_molasses_hook(self):
        self.set_fields_xodt_molasses()
        self.dipole_trap_molasses_hook_first_xodt_molasses()
        self.dipole_trap_molasses_hook_cool_molasses()

    @kernel
    def dipole_trap_molasses_hook_cool_molasses(self):
        """
        Adiabatically cool after the molasses
        """
        self.cool_molasses.do_phase()


class XODTDoubleMolassesMixin(XODTSingleMolassesMixin):
    """
    Loads atoms into a dipole trap after the narrowband red MOT, and implements a
    ramping molasses and bias magnetic field.


    This is a mixin - see the documentation for :mod:`~.dipole_trap_experiment` for
    details.

    Kernel hooks used (multiple mixins cannot use the same hooks):

    * :meth:`~DMA_initialization_hook`
    * :meth:`~dipole_trap_molasses_hook`

    We override this to do nothing since this Mixin is now taking charge of field setting:

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

        self.molasses_xodt_2.bind_suservo_setpoint_params_to_default_beam_setter(
            [
                self.red_mot.red_beam_controller.all_beam_default_setter,
                self.dipole_beam_controller.all_beam_default_setter,
                self.transparency_setter,
            ]
        )

        # self.molasses_xodt_2.daisy_chain_with_previous_phase(
        #     self.molasses_xodt_1, suservos=suservos_XODT
        # )

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
        self.set_fields_xodt_molasses()
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
    * :meth:`~post_narrowband_hook`
    * :meth:`~dipole_trap_molasses_hook`
    * :meth:`~dipole_trap_evaporation_hook`

    We override this to do nothing since this Mixin is now taking charge of field setting:

    * :meth:`~set_postnarrowband_fields_hook`
    """

    def build_fragment(self):
        super().build_fragment()

        self.ramp_during_evap_phase.daisy_chain_with_previous_phase(
            self.molasses_xodt_2, suservos=SUSERVOS_XODT
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
    * :meth:`~post_narrowband_hook`
    * :meth:`~dipole_trap_molasses_hook`
    * :meth:`~dipole_trap_evaporation_hook`

    We override this to do nothing since this Mixin is now taking charge of field setting:

    * :meth:`~set_postnarrowband_fields_hook`
    """

    def build_fragment(self):
        super().build_fragment()

        self.ramp_during_evap_phase.daisy_chain_with_previous_phase(
            self.molasses_xodt_1, suservos=SUSERVOS_XODT
        )

    @kernel
    def DMA_initialization_hook(self):
        self.DMA_initialization_hook_default()
        self.DMA_initialization_hook_xodt_molasses()
        self.DMA_initialization_hook_evap_with_field_ramp()


class ClearOut689Mixin(DipoleTrapWithExperiment):
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
        )
        self.setpoint_487_during_clearout: FloatParamHandle

        super().build_fragment()

    @kernel
    def do_clearout_pulse_hook(self):
        self.transparency_suservo_clearout.set_suservo(
            amplitude=1.0,
            freq=TRANSPARENCY_AOM_FREQ,
            rf_switch_state=True,
            enable_iir=True,
            setpoint_v=self.setpoint_487_during_clearout.get(),
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
        self.transparency_suservo_clearout.set_channel_state(
            rf_switch_state=False, enable_iir=False
        )
        # self.transparency_suservo_clearout.set_channel_state(
        #     rf_switch_state=False, enable_iir=False
        # )
