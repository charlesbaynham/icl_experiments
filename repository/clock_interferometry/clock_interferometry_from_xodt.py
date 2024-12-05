import logging

from artiq.experiment import kernel
from ndscan.experiment.entry_point import make_fragment_scan_exp

from repository.lib.experiment_templates.dipole_trap_experiment import (
    DipoleTrapWithExperiment,
)
from repository.lib.experiment_templates.mixins.andor_imaging.double_trap_imaging import (
    DoubleTrapImagingNormalised,
)
from repository.lib.experiment_templates.mixins.andor_imaging.em_gain import EMGain
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
from repository.lib.experiment_templates.mixins.XODT_molasses import (
    XODTSingleMolassesPlusFieldRampMixin,
)
from repository.lib.experiment_templates.mixins.rigol_counter_mixin import (
    RigolCounterMixin,
)

logger = logging.getLogger(__name__)


class DifferentialClockInterferometryFrag(
    ClockInterferometryDipoleTrapMixin,
    ClockShelvingAndClearoutDipoleTrapMixin,
    DoubleTrapImagingNormalised,
    EMGain,
    FLIRBlueMOTMeasurementMixin,
    XODTSingleMolassesPlusFieldRampMixin,
    OpticalPumpingWithFieldSettingDipoleTrapMixin,
    RigolCounterMixin,
    DipoleTrapWithExperiment,
):
    """
    Clock interferometry from a double XODT
    """

    @kernel
    def before_start_hook(self):
        self.before_start_hook_clockspec()
        self.before_start_hook_xodt_molasses()
        self.before_start_hook_clockshelving()


class DifferentialClockInterferometryWithNoiseFrag(
    ClockInterferometryWithNoiseDipoleTrapMixin,
    ClockShelvingAndClearoutDipoleTrapMixin,
    DoubleTrapImagingNormalised,
    EMGain,
    FLIRBlueMOTMeasurementMixin,
    XODTSingleMolassesPlusFieldRampMixin,
    OpticalPumpingWithFieldSettingDipoleTrapMixin,
    RigolCounterMixin,
    DipoleTrapWithExperiment,
):
    """
    Clock interferometry from a double XODT with added noise
    """

    @kernel
    def before_start_hook(self):
        self.before_start_hook_clockspec()
        self.before_start_hook_xodt_molasses()
        self.before_start_hook_clockshelving()


DifferentialClockInterferometry = make_fragment_scan_exp(
    DifferentialClockInterferometryFrag
)


DifferentialClockInterferometryWithNoise = make_fragment_scan_exp(
    DifferentialClockInterferometryWithNoiseFrag
)
