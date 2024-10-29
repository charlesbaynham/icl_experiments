import logging

from artiq.experiment import kernel
from ndscan.experiment.entry_point import make_fragment_scan_exp

from repository.lib.experiment_templates.mixins.andor_imaging.triple_imaging_basic import (
    TripleImageBasicMixin,
)
from repository.lib.experiment_templates.mixins.clock_interferometry import (
    ClockInterferometryMixin,
)
from repository.lib.experiment_templates.mixins.clock_pumping import (
    ClockShelvingAndClearoutRedMOTMixin,
)
from repository.lib.experiment_templates.mixins.flir_blue_mot_measurement import (
    FLIRBlueMOTMeasurementMixin,
)

logger = logging.getLogger(__name__)


class MOTClockInterferometryNormalizedExp(
    ClockInterferometryMixin,
    ClockShelvingAndClearoutRedMOTMixin,
    FLIRBlueMOTMeasurementMixin,
    # TripleImageFastKineticsMixin,  # TODO: go back to fast kinetics
    TripleImageBasicMixin,
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
