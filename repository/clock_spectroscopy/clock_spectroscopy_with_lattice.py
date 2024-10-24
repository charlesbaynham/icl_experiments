import logging

from ndscan.experiment.entry_point import make_fragment_scan_exp

from repository.lib.experiment_templates.mixins.clock_spectroscopy import (
    ClockSpectroscopyMixin,
)
from repository.lib.experiment_templates.mixins.flir_blue_mot_measurement import (
    FLIRBlueMOTMeasurementMixin,
)
from repository.lib.experiment_templates.mixins.pumped_lattice import (
    DroppedPumpedLatticeMixin,
)
from repository.lib.experiment_templates.mixins.single_andor_image import (
    SingleAndorImage,
)
from repository.lib.experiment_templates.mixins.triple_imaging_kinetics import (
    TripleImageFastKineticsMixin,
)
from repository.lib.experiment_templates.red_mot_experiment import RedMOTWithExperiment

logger = logging.getLogger(__name__)


class ClockSpecFromLatticeFrag(
    ClockSpectroscopyMixin,
    DroppedPumpedLatticeMixin,
    TripleImageFastKineticsMixin,
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
    ClockSpectroscopyMixin,
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


ClockSpecFromLattice = make_fragment_scan_exp(ClockSpecFromLatticeFrag)
BasicClockSpecFromLattice = make_fragment_scan_exp(BasicClockSpecFromLatticeFrag)
