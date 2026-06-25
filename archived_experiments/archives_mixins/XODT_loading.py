import logging

from artiq.language import kernel

from repository.lib.experiment_templates.mixins.XODT_loading import LoadSingleXODTMixin
from repository.lib.fragments.dipole_trap.dipole_trap_phases import DipoleRamp1064

logger = logging.getLogger(__name__)


class LoadSingleXODTWithRampUpMixin(LoadSingleXODTMixin):
    """
    Loads atoms in a single XODT after the narrowband red MOT, then
    turns off MOT beams and ramps up dipole trap beam for the atoms to stay in a deeper trap.

    Ramps the dipole trap beams on at the start of a stage of ramping MOT beams.

    Kernel hooks used (multiple mixins cannot use the same hooks):

    * :meth:`~DMA_initialization_checkpoint`
    * :meth:`~post_narrowband_hook`
    * :meth:`~dipole_trap_loading_hook`

    We also override this hook to do nothing since this Mixin is now taking
    charge of field setting:

    * :meth:`~set_postnarrowband_fields_hook`
    """

    def build_fragment(self):
        super().build_fragment()

        self.setattr_fragment("dipole_ramp_up", DipoleRamp1064)
        self.dipole_ramp_up: DipoleRamp1064

        self.dipole_ramp_up.daisy_chain_with_previous_phase(
            self.mot_in_xodt, suservos=["suservo_aom_1064_delivery"]
        )

    @kernel
    def DMA_initialization_checkpoint(self):
        self.DMA_initialization_checkpoint_subfragments()
        self.DMA_initialization_checkpoint_redmot_default()
        self.DMA_initialization_checkpoint_loading_xodt_mot()

    @kernel
    def DMA_initialization_checkpoint_loading_xodt_mot(self):
        """
        Preload phases' handles. These have to be grouped together, instead of
        handled in separate subfragment setups, otherwise only the last-compiled
        dma handle is valid.
        """
        self.mot_in_xodt.precalculate_dma_handle()
        self.dipole_ramp_up.precalculate_dma_handle()

    @kernel
    def dipole_trap_loading_hook(self):
        self.dipole_trap_loading_hook_single_xodt_with_ramp_up()

    @kernel
    def dipole_trap_loading_hook_single_xodt_with_ramp_up(self):
        """
        Turn the dipole beams on and do the xodt loading ramping phase, then turn
        off the MOT beams and continue to ramp up the 1064
        """
        self.dipole_beam_controller.turn_on_dipole_beams()

        # Step the 689 stir frequency
        self.blue_3d_mot.mirny_eom_sidebands.set_689_stir_sideband_detuning(
            detuning=self.stir_beam_detuning_mot_xodt.get()
        )

        self.mot_in_xodt.do_phase()

        # turn off the mot beams
        self.red_mot.red_beam_controller.all_mot_beams_setter.turn_beams_off(
            ignore_shutters=True
        )

        # ramp up 1064
        self.dipole_ramp_up.do_phase()
