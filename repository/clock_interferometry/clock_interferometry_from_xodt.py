import logging

from artiq.language import kernel
from ndscan.experiment.entry_point import make_fragment_scan_exp

from repository.lib.experiment_templates.dipole_trap_experiment import (
    DipoleTrapWithExperiment,
)
from repository.lib.experiment_templates.mixins.andor_imaging.absorption_imaging import (
    AbsorptionDoubleDipoleTrapMixin,
)
from repository.lib.experiment_templates.mixins.andor_imaging.count_convert import (
    CountConvert,
)
from repository.lib.experiment_templates.mixins.andor_imaging.double_trap_imaging import (
    DoubleTrapImagingNormalised,
)
from repository.lib.experiment_templates.mixins.clock_interferometry import (
    ClockInterferometryDipoleTrapMixin,
)
from repository.lib.experiment_templates.mixins.clock_interferometry_with_noise import (
    ClockInterferometryWithNoiseDipoleTrapMixin,
)
from repository.lib.experiment_templates.mixins.clock_shelving import (
    ClockShelvingAndClearoutDipoleTrapMixin,
)
from repository.lib.experiment_templates.mixins.flir_blue_mot_measurement import (
    FLIRBlueMOTMeasurementMixin,
)
from repository.lib.experiment_templates.mixins.pumped_lattice import (
    OpticalPumpingWithFieldSettingDipoleTrapMixin,
)
from repository.lib.experiment_templates.mixins.rigol_counter import RigolCounterMixin
from repository.lib.experiment_templates.mixins.XODT_molasses import (
    XODTSingleMolassesPlusFieldRampMixin,
)

logger = logging.getLogger(__name__)


class DifferentialClockInterferometryFrag(
    ClockInterferometryDipoleTrapMixin,
    ClockShelvingAndClearoutDipoleTrapMixin,
    DoubleTrapImagingNormalised,
    CountConvert,
    RigolCounterMixin,
    FLIRBlueMOTMeasurementMixin,
    XODTSingleMolassesPlusFieldRampMixin,
    OpticalPumpingWithFieldSettingDipoleTrapMixin,
    DipoleTrapWithExperiment,
):
    """
    Clock interferometry from a double XODT
    """

    @kernel
    def before_start_hook(self):
        self.before_start_hook_clockspec()
        self.before_start_hook_clockshelving()


class DifferentialClockInterferometryWithNoiseFrag(
    ClockInterferometryWithNoiseDipoleTrapMixin,
    ClockShelvingAndClearoutDipoleTrapMixin,
    DoubleTrapImagingNormalised,
    CountConvert,
    RigolCounterMixin,
    FLIRBlueMOTMeasurementMixin,
    XODTSingleMolassesPlusFieldRampMixin,
    OpticalPumpingWithFieldSettingDipoleTrapMixin,
    DipoleTrapWithExperiment,
):
    """
    Clock interferometry from a double XODT with added noise
    """

    @kernel
    def before_start_hook(self):
        self.before_start_hook_clockspec()
        self.before_start_hook_clockshelving()


class AbsImagingDifferentialClockInterferometryWithNoiseFrag(
    ClockInterferometryWithNoiseDipoleTrapMixin,
    ClockShelvingAndClearoutDipoleTrapMixin,
    AbsorptionDoubleDipoleTrapMixin,
    FLIRBlueMOTMeasurementMixin,
    RigolCounterMixin,
    XODTSingleMolassesPlusFieldRampMixin,
    OpticalPumpingWithFieldSettingDipoleTrapMixin,
    DipoleTrapWithExperiment,
):
    """
    Absorption imaging clock interferometry from a double XODT with added noise
    """

    @kernel
    def before_start_hook(self):
        self.before_start_hook_clockspec()
        self.before_start_hook_clockshelving()


DifferentialClockInterferometry = make_fragment_scan_exp(
    DifferentialClockInterferometryFrag
)


DifferentialClockInterferometryWithNoise = make_fragment_scan_exp(
    DifferentialClockInterferometryWithNoiseFrag
)

AbsImagingDifferentialClockInterferometryWithNoise = make_fragment_scan_exp(
    AbsImagingDifferentialClockInterferometryWithNoiseFrag
)
