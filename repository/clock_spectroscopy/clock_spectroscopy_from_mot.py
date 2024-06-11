import logging

from ndscan.experiment.entry_point import make_fragment_scan_exp
from pyaion.models import UrukuledBeam

from repository.lib import constants
from repository.lib.fragments.red_mot.red_mot_mixins.clock_spectroscopy import (
    ClockSpectroscopyMixin,
)
from repository.lib.fragments.red_mot.red_mot_mixins.single_andor_image import (
    SingleAndorImage,
)
from repository.lib.fragments.red_mot.red_mot_mixins.triple_imaging_binned import (
    TripleImageBinnedMixin,
)


logger = logging.getLogger(__name__)


class MOTClockSpectroscopyExp(ClockSpectroscopyMixin, SingleAndorImage):
    """
    Basic clock spectroscopy from a red MOT

    Use the up clock beam for spectroscopy, altering the (single-pass) AOM

    Image the ground state atoms only
    """

    pass


class MOTClockSpectroscopyNormalizedExp(ClockSpectroscopyMixin, TripleImageBinnedMixin):
    """
    Normalised clock spectroscopy from a red MOT

    Use the up clock beam for spectroscopy, altering the (single-pass) AOM

    Image the ground state atoms, repump and image the excited state, then image
    once more for background
    """

    pass


MOTClockSpectroscopy = make_fragment_scan_exp(MOTClockSpectroscopyExp)
MOTClockSpectroscopyNormalized = make_fragment_scan_exp(
    MOTClockSpectroscopyNormalizedExp
)
