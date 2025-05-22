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
    CountConvertWithEMGain,
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
from repository.lib.experiment_templates.mixins.XODT_loading import LoadSingleXODTMixin
from repository.lib.experiment_templates.mixins.XODT_molasses import (
    FieldOnlyRampInEvapMixin,
)

logger = logging.getLogger(__name__)


class _DifferentialClockInterferometryImaging(
    DoubleTrapImagingNormalised,
    CountConvertWithEMGain,
    FLIRBlueMOTMeasurementMixin,
):
    """
    Seperate the imaging setup so we can also use absorption imaging
    """


class _DifferentialClockInterferometry(
    # Clock interferometry:
    ClockInterferometryDipoleTrapMixin,
    # Velocity slicing:
    ClockShelvingAndClearoutDipoleTrapMixin,
    # Spin polarisation:
    OpticalPumpingWithFieldSettingDipoleTrapMixin,
    FieldOnlyRampInEvapMixin,
    # Extra monitoring:
    RigolCounterMixin,
    # Loading:
    LoadSingleXODTMixin,
    # Base:
    DipoleTrapWithExperiment,
):
    @kernel
    def before_start_hook(self):
        self.before_start_hook_clockspec()
        self.before_start_hook_clockshelving()

    @kernel
    def DMA_initialization_hook(self):
        self.DMA_initialization_hook_default()
        self.DMA_initialization_hook_evap_with_field_ramp()
        self.DMA_initialization_hook_loading_xodt_mot()


class DifferentialClockInterferometryFrag(
    _DifferentialClockInterferometry,
    _DifferentialClockInterferometryImaging,
):
    """
    Clock interferometry from a double XODT
    """


class DifferentialClockInterferometryWithNoiseFrag(
    _DifferentialClockInterferometry,
    _DifferentialClockInterferometryImaging,
    ClockInterferometryWithNoiseDipoleTrapMixin,
):
    """
    Clock interferometry from a double XODT with added noise
    """


class AbsImagingDifferentialClockInterferometryWithNoiseFrag(
    _DifferentialClockInterferometry,
    AbsorptionDoubleDipoleTrapMixin,
    ClockInterferometryWithNoiseDipoleTrapMixin,
):
    """
    Absorption imaging clock interferometry from a double XODT with added noise
    """


DifferentialClockInterferometry = make_fragment_scan_exp(
    DifferentialClockInterferometryFrag
)
DifferentialClockInterferometryWithNoise = make_fragment_scan_exp(
    DifferentialClockInterferometryWithNoiseFrag
)
AbsImagingDifferentialClockInterferometryWithNoise = make_fragment_scan_exp(
    AbsImagingDifferentialClockInterferometryWithNoiseFrag
)
