import logging

from ndscan.experiment.entry_point import make_fragment_scan_exp
from pyaion.models import UrukuledBeam

from repository.lib import constants
from repository.lib.fragments.beams.urukul_init import make_urukul_init
from repository.lib.fragments.beams.urukul_init import UrukulInit
from repository.lib.fragments.red_mot.red_mot_mixins.clock_spectroscopy import (
    ClockSpectroscopyMixin,
)
from repository.lib.fragments.red_mot.red_mot_mixins.triple_imaging_kinetics import (
    TripleImageMOTMixin,
)


logger = logging.getLogger(__name__)


CLOCK_BEAM_INFO: UrukuledBeam = constants.URUKULED_BEAMS["clock_up"]


class BasicClockSpectroscopyExp(ClockSpectroscopyMixin, TripleImageMOTMixin):
    """
    Basic clock spectroscopy

    Use the up clock beam for spectroscopy, altering the (single-pass) AOM

    Image the ground state atoms, repump and image the excited state, then image
    once more for background
    """

    pass


BasicClockSpectroscopy = make_fragment_scan_exp(BasicClockSpectroscopyExp)
