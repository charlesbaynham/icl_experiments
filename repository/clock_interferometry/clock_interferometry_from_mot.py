import logging

from ndscan.experiment.entry_point import make_fragment_scan_exp

from repository.lib.fragments.red_mot.red_mot_mixins.clock_interferometry import (
    ClockInterferometryMixin,
)
from repository.lib.fragments.red_mot.red_mot_mixins.clock_pumping import (
    ClockPumpingMixin,
)
from repository.lib.fragments.red_mot.red_mot_mixins.triple_imaging_kinetics import (
    TripleImageFastKineticsMixin,
)


logger = logging.getLogger(__name__)


class MOTClockInterferometryNormalizedExp(
    ClockInterferometryMixin, ClockPumpingMixin, TripleImageFastKineticsMixin
):
    """
    Clock interferometry with clock pumping and fast kinetics
    """

    pass


MOTClockInterferometryNormalized = make_fragment_scan_exp(
    MOTClockInterferometryNormalizedExp
)
