import logging

from artiq.language import kernel
from ndscan.experiment.entry_point import make_fragment_scan_exp

from repository.lib.experiment_templates.dipole_trap_experiment import (
    DipoleTrapWithExperiment,
)
from repository.lib.experiment_templates.mixins.andor_imaging.normalised_fast_kinetics import (
    NormalisedDipoleTrapFastKineticsMixin,
)
from repository.lib.experiment_templates.mixins.andor_imaging.single_andor_image import (
    SingleAndorImage,
)
from repository.lib.experiment_templates.mixins.andor_imaging.triple_imaging_fast_kinetics import (
    TripleImageDipoleTrapFastKineticsMixin,
)
from repository.lib.experiment_templates.mixins.clock_spectroscopy import (
    ClockRabiSpectroscopyDipoleTrapMixin,
)
from repository.lib.experiment_templates.mixins.clock_spectroscopy import (
    ClockRabiSpectroscopyRedMotMixin,
)
from repository.lib.experiment_templates.mixins.constant_lattice import (
    ConstantBeamsMixin,
)
from repository.lib.experiment_templates.mixins.evaporation_mixin import (
    FieldOnlyRampInEvapMixin,
)
from repository.lib.experiment_templates.mixins.flir_blue_mot_measurement import (
    FLIRBlueMOTMeasurementMixin,
)
from repository.lib.experiment_templates.mixins.optical_pumping import (
    DroppedPumpedLatticeMixin,
)
from repository.lib.experiment_templates.mixins.optical_pumping import (
    OpticalPumpingWithFieldSettingDipoleTrapMixin,
)
from repository.lib.experiment_templates.red_mot_experiment import RedMOTWithExperiment

logger = logging.getLogger(__name__)


class ClockSpecFromLatticeFrag(
    ClockRabiSpectroscopyRedMotMixin,
    DroppedPumpedLatticeMixin,
    TripleImageDipoleTrapFastKineticsMixin,
    FLIRBlueMOTMeasurementMixin,
    RedMOTWithExperiment,
):
    """
    Clock spectroscopy from dropped lattice

    Load into a lattice, pump into a stretched state, drop the atoms by ramping
    the lattice, then use the up clock beam for spectroscopy, altering the
    (single-pass) AOM.

    Image the ground state atoms, repump and image the excited state, then image
    once more for background.
    """


class BasicClockSpecFromLatticeFrag(
    ClockRabiSpectroscopyRedMotMixin,
    DroppedPumpedLatticeMixin,
    FLIRBlueMOTMeasurementMixin,
    SingleAndorImage,
):
    """
    Clock spectroscopy from dropped lattice - single image

    Load into a lattice, pump into a stretched state, drop the atoms by ramping
    the lattice, then use the up clock beam for spectroscopy, altering the
    (single-pass) AOM.

    Image only the ground state atoms
    """


class ClockSpecFromVerticalLatticeFrag(
    ClockRabiSpectroscopyDipoleTrapMixin,
    ConstantBeamsMixin,
    NormalisedDipoleTrapFastKineticsMixin,
    OpticalPumpingWithFieldSettingDipoleTrapMixin,
    FieldOnlyRampInEvapMixin,
    FLIRBlueMOTMeasurementMixin,
    DipoleTrapWithExperiment,
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
    def DMA_initialization_hook(self):
        self.DMA_initialization_hook_default()
        self.DMA_initialization_hook_evap_with_field_ramp()


ClockSpecFromLattice = make_fragment_scan_exp(ClockSpecFromLatticeFrag)
BasicClockSpecFromLattice = make_fragment_scan_exp(BasicClockSpecFromLatticeFrag)
ClockSpecFromVerticalLattice = make_fragment_scan_exp(ClockSpecFromVerticalLatticeFrag)
