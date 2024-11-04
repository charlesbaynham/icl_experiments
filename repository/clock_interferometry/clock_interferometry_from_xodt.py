import logging

from artiq.experiment import kernel
from ndscan.experiment.entry_point import make_fragment_scan_exp

from repository.lib.experiment_templates.mixins.andor_imaging.double_trap_imaging import (
    DoubleTrapImagingBGSubtracted,
)
from repository.lib.experiment_templates.mixins.clock_interferometry import (
    ClockInterferometryDipoleTrapMixin,
)
from repository.lib.experiment_templates.mixins.clock_shelving import (
    ClockShelvingAndClearoutDipoleTrapMixin,
)
from repository.lib.experiment_templates.mixins.flir_blue_mot_measurement import (
    FLIRBlueMOTMeasurementMixin,
)
from repository.lib.experiment_templates.mixins.XODT_molasses import (
    XODTMolassesPlusFieldRampMixin,
)


logger = logging.getLogger(__name__)


class DifferentialClockInterferometryFrag(
    ClockInterferometryDipoleTrapMixin,
    ClockShelvingAndClearoutDipoleTrapMixin,
    FLIRBlueMOTMeasurementMixin,
    XODTMolassesPlusFieldRampMixin,
    DoubleTrapImagingBGSubtracted,
):
    """
    Clock interferometry from a double XODT
    """

    @kernel
    def before_start_hook(self):
        self.before_start_hook_clockspec()
        self.before_start_hook_xodt_molasses()


DifferentialClockInterferometry = make_fragment_scan_exp(
    DifferentialClockInterferometryFrag
)
