import logging

from artiq.experiment import kernel
from ndscan.experiment.entry_point import make_fragment_scan_exp

from repository.lib.experiment_templates.mixins.andor_imaging.em_gain import EMGain
from repository.lib.experiment_templates.mixins.andor_imaging.normalised_fast_kinetics import (
    NormalisedRedMOTFastKineticsMixin,
)
from repository.lib.experiment_templates.mixins.clock_interferometry import (
    ClockInterferometryRedMOTMixin,
)
from repository.lib.experiment_templates.mixins.clock_interferometry import (
    ClockInterferometryWithSUServoMixin,
)
from repository.lib.experiment_templates.mixins.flir_blue_mot_measurement import (
    FLIRBlueMOTMeasurementMixin,
)

logger = logging.getLogger(__name__)


class MOTClockInterferometryNormalizedExp(
    ClockInterferometryRedMOTMixin,
    # ClockShelvingAndClearoutRedMOTMixin, # FIXME
    FLIRBlueMOTMeasurementMixin,
    NormalisedRedMOTFastKineticsMixin,
):
    """
    Clock interferometry from red MOT with clock shelving and fast kinetics
    """

    @kernel
    def before_start_hook(self):
        # self.before_start_hook_clockshelving() # FIXME
        self.before_start_hook_clockspec()


class MOTClockInterferometrySUServoExp(
    ClockInterferometryRedMOTMixin,
    ClockInterferometryWithSUServoMixin,
    # ClockShelvingAndClearoutRedMOTMixin,  # FIXME
    FLIRBlueMOTMeasurementMixin,
    NormalisedRedMOTFastKineticsMixin,
    EMGain,  # FIXME
):
    """
    Clock interferometry from red MOT using SUServo

    Use the SUServo for phase-steps instead of the clock switch
    """

    @kernel
    def before_start_hook(self):
        self.before_start_hook_clockinterferometry()
        # self.before_start_hook_clockshelving()  # FIXME
        self.before_start_hook_clockspec()


MOTClockInterferometryNormalized = make_fragment_scan_exp(
    MOTClockInterferometryNormalizedExp
)
MOTClockInterferometrySUServo = make_fragment_scan_exp(MOTClockInterferometrySUServoExp)
