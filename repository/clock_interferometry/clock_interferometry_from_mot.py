import logging

from artiq.language import kernel
from ndscan.experiment.entry_point import make_fragment_scan_exp

from repository.lib.experiment_templates.mixins.andor_imaging.em_gain import EMGain
from repository.lib.experiment_templates.mixins.andor_imaging.normalised_fast_kinetics import (
    NormalisedRedMOTFastKineticsMixin,
)
from repository.lib.experiment_templates.mixins.clock_interferometry import (
    ClockInterferometryRedMOTMixin,
)
from repository.lib.experiment_templates.mixins.clock_shelving import (
    ClockShelvingAndClearoutRedMOTMixin,
)
from repository.lib.experiment_templates.mixins.flir_blue_mot_measurement import (
    FLIRBlueMOTMeasurementMixin,
)

logger = logging.getLogger(__name__)


class MOTClockInterferometryNormalizedExp(
    ClockInterferometryRedMOTMixin,
    ClockShelvingAndClearoutRedMOTMixin,
    FLIRBlueMOTMeasurementMixin,
    NormalisedRedMOTFastKineticsMixin,
    EMGain,
):
    """
    Clock interferometry from red MOT with clock shelving and fast kinetics
    """

    @kernel
    def before_start_hook(self):
        self.before_start_hook_clockshelving()
        self.before_start_hook_clockspec()


MOTClockInterferometryNormalized = make_fragment_scan_exp(
    MOTClockInterferometryNormalizedExp
)
