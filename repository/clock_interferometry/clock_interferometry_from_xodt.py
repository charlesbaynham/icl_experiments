import logging

from artiq.language import kernel
from ndscan.experiment.entry_point import make_fragment_scan_exp

from repository.lib.experiment_templates.mixins.andor_imaging.absorption_imaging import (
    AbsorptionDoubleDipoleTrapMixin,
)
from repository.lib.experiment_templates.mixins.andor_imaging.count_convert import (
    CountConvertWithEMGainMixin,
)
from repository.lib.experiment_templates.mixins.andor_imaging.double_trap_imaging import (
    DoubleTrapImagingRepumpedNormalisedMixin,
)
from repository.lib.experiment_templates.mixins.cavity_relocking import (
    MonitorAndRelock689and698Mixin,
)
from repository.lib.experiment_templates.mixins.clock_interferometry import (
    ClockInterferometryBase,
)
from repository.lib.experiment_templates.mixins.clock_interferometry import (
    ClockInterferometryDipoleTrapMixin,
)
from repository.lib.experiment_templates.mixins.clock_interferometry_with_noise import (
    ClockInterferometryWithNoiseDipoleTrapMixin,
)
from repository.lib.experiment_templates.mixins.clock_interferometry_with_signal import (
    StarkShifterWithSignalMixin,
)
from repository.lib.experiment_templates.mixins.clock_shelving import (
    ClockShelvingAndClearoutDipoleTrapMixin,
)
from repository.lib.experiment_templates.mixins.doppler_compensation import (
    DopplerCompensationForInterferometryMixin,
)
from repository.lib.experiment_templates.mixins.evaporation_mixin import (
    FieldOnlyRampInEvapMixin,
)
from repository.lib.experiment_templates.mixins.flir_blue_mot_measurement import (
    FLIRBlueMOTMeasurementMixin,
)
from repository.lib.experiment_templates.mixins.optical_pumping import (
    OpticalPumpingWithFieldSettingDipoleTrapMixin,
)
from repository.lib.experiment_templates.mixins.XODT_loading import (
    LoadXXODTWithTransparencyBeamMixin,
)

# from repository.lib.experiment_templates.mixins.clock_glitch_counting import (
#     ClockGlitchCounterMixin,
# )

logger = logging.getLogger(__name__)


class _DifferentialClockInterferometryImaging(
    DoubleTrapImagingRepumpedNormalisedMixin,
    CountConvertWithEMGainMixin,
    FLIRBlueMOTMeasurementMixin,
):
    """
    Separate the imaging setup so we can also use absorption imaging
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
    # ClockGlitchCounterMixin,
    MonitorAndRelock689and698Mixin,
    # Loading:
    LoadXXODTWithTransparencyBeamMixin,
    # Base:
    ClockInterferometryBase,
):
    pass


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
    # ClockInterferometryWithNoiseDipoleTrapMixin,
    # DopplerCompensationForInterferometryMixin,
):
    """
    Clock interferometry from a double XODT with added noise
    """


class DifferentialClockInterferometryWithNoiseAndSignalFrag(
    _DifferentialClockInterferometry,
    _DifferentialClockInterferometryImaging,
    StarkShifterWithSignalMixin,
    ClockInterferometryWithNoiseDipoleTrapMixin,
    DopplerCompensationForInterferometryMixin,
):
    """
    Clock interferometry from a double XODT with signal and noise
    """

    @kernel
    def host_functions_after_experiment_hook(self):
        self.host_functions_after_experiment_hook_default()
        self.host_functions_after_experiment_hook_signal_injection()
        # self.host_functions_after_experiment_hook_glitch_counter()


class AbsImagingDifferentialClockInterferometryWithNoiseFrag(
    _DifferentialClockInterferometry,
    AbsorptionDoubleDipoleTrapMixin,
    ClockInterferometryWithNoiseDipoleTrapMixin,
    DopplerCompensationForInterferometryMixin,
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
DifferentialClockInterferometryWithNoiseAndSignal = make_fragment_scan_exp(
    DifferentialClockInterferometryWithNoiseAndSignalFrag, max_rtio_underflow_retries=0
)
AbsImagingDifferentialClockInterferometryWithNoise = make_fragment_scan_exp(
    AbsImagingDifferentialClockInterferometryWithNoiseFrag
)
