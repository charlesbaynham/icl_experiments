import logging

from artiq.language import kernel
from ndscan.experiment.entry_point import make_fragment_scan_exp

from repository.lib.experiment_templates.dipole_trap_experiment import (
    DipoleTrapWithExperimentBase,
)
from repository.lib.experiment_templates.mixins.andor_imaging.normalised_fast_kinetics import (
    NormalisedDipoleTrapFastKineticsMixin,
)
from repository.lib.experiment_templates.mixins.clock_spectroscopy import (
    ClockRabiSpectroscopyDipoleTrapMixin,
)
from repository.lib.experiment_templates.mixins.evaporation_mixin import (
    FieldOnlyRampInEvapMixin,
)
from repository.lib.experiment_templates.mixins.flir_blue_mot_measurement import (
    FLIRBlueMOTMeasurementMixin,
)
from repository.lib.experiment_templates.mixins.optical_pumping import (
    OpticalPumpingWithFieldSettingDipoleTrapMixin,
)

logger = logging.getLogger(__name__)


class ClockSpecFromVerticalLatticeFrag(
    ClockRabiSpectroscopyDipoleTrapMixin,
    NormalisedDipoleTrapFastKineticsMixin,
    OpticalPumpingWithFieldSettingDipoleTrapMixin,
    FieldOnlyRampInEvapMixin,
    FLIRBlueMOTMeasurementMixin,
    DipoleTrapWithExperimentBase,
):
    """
    Clock spectroscopy from vertical lattice

    Load into a vertical lattice, then use the up clock beam for spectroscopy, altering the
    (single-pass) AOM.

    Image the ground state atoms, repump and image the excited state, then image
    once more for background.
    """

    # keep dipole beams on
    @kernel
    def post_dipole_trap_hook(self):
        pass

    @kernel
    def DMA_initialization_checkpoint(self):
        self.DMA_initialization_checkpoint_subfragments()
        self.DMA_initialization_checkpoint_redmot_default()
        self.DMA_initialization_checkpoint_dipole_trap_default()
        self.DMA_initialization_checkpoint_evap_with_field_ramp()


ClockSpecFromVerticalLattice = make_fragment_scan_exp(ClockSpecFromVerticalLatticeFrag)
