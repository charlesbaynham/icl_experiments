import logging

from artiq.language import kernel
from ndscan.experiment.entry_point import make_fragment_scan_exp

from repository.lib.experiment_templates.mixins.andor_imaging.single_andor_image import (
    SingleAndorImage,
)

from repository.lib.experiment_templates.mixins.clock_spectroscopy import (
    ClockRabiSpectroscopyRedMotMixin,
)
from repository.lib.experiment_templates.mixins.flir_blue_mot_measurement import (
    FLIRBlueMOTMeasurementMixin,
)
from repository.lib.experiment_templates.mixins.optical_pumping import (
    DroppedPumpedLatticeMixin,
)


logger = logging.getLogger(__name__)


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


BasicClockSpecFromLattice = make_fragment_scan_exp(BasicClockSpecFromLatticeFrag)
