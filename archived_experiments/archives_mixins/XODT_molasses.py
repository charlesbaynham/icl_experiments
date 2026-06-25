from artiq.language import delay
from artiq.language import kernel
from ndscan.experiment.parameters import FloatParam
from ndscan.experiment.parameters import FloatParamHandle

from repository.lib import constants
from repository.lib.experiment_templates.mixins.evaporation_mixin import (
    EvapAndFieldRampBase,
)
from repository.lib.experiment_templates.mixins.XODT_molasses import (
    EvapAndFieldRampBase,
)
from repository.lib.experiment_templates.mixins.XODT_molasses import (
    XODTSingleMolassesMixin,
)
from repository.lib.fragments.dipole_trap.dipole_trap_phases import SUSERVOS_XODT
from repository.lib.fragments.dipole_trap.dipole_trap_phases import MolassesInXODT_2


class XODTDoubleMolassesMixin(XODTSingleMolassesMixin):
    """
    Loads atoms into a dipole trap after the narrowband red MOT, and implements a
    ramping molasses and bias magnetic field.


    This is a mixin - see the documentation for :mod:`~.dipole_trap_experiment` for
    details.

    Kernel hooks used (multiple mixins cannot use the same hooks):

    * :meth:`~DMA_initialization_checkpoint`
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
    def DMA_initialization_checkpoint(self):
        self.DMA_initialization_checkpoint_subfragments()
        self.DMA_initialization_checkpoint_redmot_default()
        self.DMA_initialization_checkpoint_xodt_molasses()

    @kernel
    def DMA_initialization_checkpoint_xodt_molasses(self):
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

    * :meth:`~DMA_initialization_checkpoint`
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
    def DMA_initialization_checkpoint(self):
        self.DMA_initialization_checkpoint_subfragments()
        self.DMA_initialization_checkpoint_redmot_default()
        self.DMA_initialization_checkpoint_xodt_molasses()
        self.DMA_initialization_checkpoint_evap_with_field_ramp()
