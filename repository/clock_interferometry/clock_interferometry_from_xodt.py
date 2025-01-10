import logging

from artiq.experiment import kernel
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
from repository.lib.experiment_templates.mixins.check_for_relocks import (
    CheckForRelocksMixin,
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
from repository.lib.experiment_templates.mixins.XODT_molasses import (
    XODTSingleMolassesPlusFieldRampMixin,
)
from repository.lib.fragments.rigol_counter import RigolCounterFrag

logger = logging.getLogger(__name__)


class CheckRigolMixin(DipoleTrapWithExperiment):
    def build_fragment(self):
        super().build_fragment()

        self.setattr_fragment("rigol", RigolCounterFrag)
        self.rigol: RigolCounterFrag


class DifferentialClockInterferometryFrag(
    ClockInterferometryDipoleTrapMixin,
    ClockShelvingAndClearoutDipoleTrapMixin,
    DoubleTrapImagingNormalised,
    CountConvert,
    FLIRBlueMOTMeasurementMixin,
    XODTSingleMolassesPlusFieldRampMixin,
    OpticalPumpingWithFieldSettingDipoleTrapMixin,
    CheckRigolMixin,
    CheckForRelocksMixin,
    DipoleTrapWithExperiment,
):
    """
    Clock interferometry from a double XODT
    """

    @kernel
    def before_start_hook(self):  # FIXME remove this
        self.before_start_hook_clockspec()
        self.before_start_hook_clockshelving()


class DifferentialClockInterferometryWithNoiseFrag(
    ClockInterferometryWithNoiseDipoleTrapMixin,
    ClockShelvingAndClearoutDipoleTrapMixin,
    DoubleTrapImagingNormalised,
    CountConvert,
    FLIRBlueMOTMeasurementMixin,
    XODTSingleMolassesPlusFieldRampMixin,
    OpticalPumpingWithFieldSettingDipoleTrapMixin,
    CheckRigolMixin,
    DipoleTrapWithExperiment,
):
    """
    Clock interferometry from a double XODT with added noise
    """

    @kernel
    def before_start_hook(self):  # FIXME remove this
        self.before_start_hook_clockspec()
        self.before_start_hook_clockshelving()


class AbsImagingDifferentialClockInterferometryWithNoiseFrag(
    ClockInterferometryWithNoiseDipoleTrapMixin,
    ClockShelvingAndClearoutDipoleTrapMixin,
    AbsorptionDoubleDipoleTrapMixin,
    FLIRBlueMOTMeasurementMixin,
    XODTSingleMolassesPlusFieldRampMixin,
    OpticalPumpingWithFieldSettingDipoleTrapMixin,
    CheckRigolMixin,
    DipoleTrapWithExperiment,
):
    """
    Absorption imaging clock interferometry from a double XODT with added noise
    """

    @kernel
    def before_start_hook(self):  # FIXME remove this
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
