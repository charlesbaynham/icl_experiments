import logging

from artiq.experiment import kernel
from ndscan.experiment.entry_point import make_fragment_scan_exp

from repository.lib.fragments.red_mot.red_mot_mixins.clock_interferometry import (
    ClockInterferometryMixin,
)
from repository.lib.fragments.red_mot.red_mot_mixins.clock_pumping import (
    ClockPumpingMixin,
)
from repository.lib.fragments.red_mot.red_mot_mixins.flir_blue_mot_measurement import (
    FLIRBlueMOTMeasurementMixin,
)
from repository.lib.fragments.red_mot.red_mot_mixins.triple_imaging_kinetics import (
    TripleImageFastKineticsMixin,
)

logger = logging.getLogger(__name__)


class MOTClockInterferometryNormalizedExp(
    ClockInterferometryMixin,
    ClockPumpingMixin,
    FLIRBlueMOTMeasurementMixin,
    TripleImageFastKineticsMixin,
):
    """
    Clock interferometry with clock pumping and fast kinetics
    """

    @kernel
    def before_start_hook(self):
        self.before_start_hook_clockpumping()
        self.before_start_hook_clockspec()


MOTClockInterferometryNormalized = make_fragment_scan_exp(
    MOTClockInterferometryNormalizedExp
)
