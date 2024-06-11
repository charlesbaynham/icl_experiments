import logging

from ndscan.experiment.entry_point import make_fragment_scan_exp

from repository.lib.fragments.red_mot.red_mot_mixins.clock_pumping import (
    ClockPumpingMixin,
)
from repository.lib.fragments.red_mot.red_mot_mixins.clock_spectroscopy import (
    ClockSpectroscopyMixin,
)
from repository.lib.fragments.red_mot.red_mot_mixins.single_andor_image import (
    SingleAndorImage,
)
from repository.lib.fragments.red_mot.red_mot_mixins.triple_imaging_kinetics import (
    TripleImageFastKineticsMixin,
)


logger = logging.getLogger(__name__)


class MOTClockSpectroscopyExp(ClockSpectroscopyMixin, SingleAndorImage):
    """
    Basic clock spectroscopy from a red MOT

    Use the up clock beam for spectroscopy, altering the (single-pass) AOM

    Image the ground state atoms only
    """

    pass


class MOTClockSpectroscopyNormalizedExp(
    ClockSpectroscopyMixin, TripleImageFastKineticsMixin
):
    """
    Normalised clock spectroscopy from a red MOT

    Use the up clock beam for spectroscopy, altering the (single-pass) AOM

    Image the ground state atoms, repump and image the excited state, then image
    once more for background
    """

    pass


class MOTPumpedClockSpectroscopyNormalizedExp(
    ClockSpectroscopyMixin, ClockPumpingMixin, TripleImageFastKineticsMixin
):
    """
    Normalised clock spectroscopy from a red MOT with clock pumping

    Use the up clock beam for spectroscopy, altering the (single-pass) AOM.

    * Before spectroscopy, do a clock pulse and blast away residual ground-state
    atoms.

    * Do a clock pulse.

    * Image the ground state atoms, repump and image the excited state, then image
    once more for background
    """

    pass


MOTClockSpectroscopy = make_fragment_scan_exp(MOTClockSpectroscopyExp)
MOTClockSpectroscopyNormalized = make_fragment_scan_exp(
    MOTClockSpectroscopyNormalizedExp
)
MOTPumpedClockSpectroscopyNormalized = make_fragment_scan_exp(
    MOTPumpedClockSpectroscopyNormalizedExp
)
