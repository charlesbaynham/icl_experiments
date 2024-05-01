import logging

from ndscan.experiment.entry_point import make_fragment_scan_exp

from repository.lib.fragments.red_mot.red_mot_experiment import RedMOTWithExperiment
from repository.lib.fragments.red_mot.red_mot_mixins.clock_spectroscopy import (
    ClockSpectroscopyMixin,
)
from repository.lib.fragments.red_mot.red_mot_mixins.pumped_lattice import (
    DroppedPumpedLatticeMixin,
)
from repository.lib.fragments.red_mot.red_mot_mixins.triple_imaging_kinetics import (
    TripleImageMOTMixin,
)


logger = logging.getLogger(__name__)


class ClockSpecFromLatticeFrag(
    ClockSpectroscopyMixin,
    DroppedPumpedLatticeMixin,
    TripleImageMOTMixin,
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

    pass


ClockSpecFromLattice = make_fragment_scan_exp(ClockSpecFromLatticeFrag)
