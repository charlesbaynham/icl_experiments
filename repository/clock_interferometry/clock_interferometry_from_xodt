import logging

from artiq.experiment import kernel
from ndscan.experiment.entry_point import make_fragment_scan_exp

from repository.lib.experiment_templates.mixins.XODT_molasses import XODTMolassesMixin


from repository.lib.experiment_templates.mixins.andor_imaging.double_trap_imaging import (
    DoubleTrapImagingBGSubtracted,
)
from repository.lib.experiment_templates.mixins.clock_interferometry import (
    ClockInterferometryMixin,
)
from repository.lib.experiment_templates.mixins.clock_pumping import ClockPumpingMixin
from repository.lib.experiment_templates.mixins.flir_blue_mot_measurement import (
    FLIRBlueMOTMeasurementMixin,
)

logger = logging.getLogger(__name__)


class DifferentialClockInterferometryFrag(
    ClockInterferometryMixin,
    ClockPumpingMixin,
    FLIRBlueMOTMeasurementMixin,
    XODTMolassesMixin,
    DoubleTrapImagingBGSubtracted,
):
    """
    Clock interferometry from the double XODTs
    """

    @kernel
    def before_start_hook(self):
        self.before_start_hook_clockpumping()
        self.before_start_hook_clockspec()
        self.before_start_hook_xodt_molasses()

    @kernel
    def post_narrowband_hook(self):
        self.post_narrowband_hook_clock_pumping()
        self.post_narrowband_hook_xodt_molasses()


DifferentialClockInterferometry = make_fragment_scan_exp(
    DifferentialClockInterferometryFrag
)
