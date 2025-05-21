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
    Loads atoms in a single XODT after the narrowband red MOT. Turns the dipole beams on at the start of a stage of ramping MOT beams.

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

        self.red_mot.red_beam_controller.all_mot_beams_setter.turn_beams_on(  # FIXME Ask Alice about this - why is it needed?
            ignore_shutters=True
        )

        # Step the 689 stir frequency
        self.blue_3d_mot.mirny_eom_sidebands.set_689_stir_sideband_detuning(
            detuning=self.stir_beam_detuning_mot_xodt.get()
        )

        self.mot_xodt.do_phase()
