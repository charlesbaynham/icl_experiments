import logging

from artiq.language import kernel
from ndscan.experiment.entry_point import make_fragment_scan_exp

from repository.lib.experiment_templates.dipole_trap_experiment import (
    DipoleTrapWithExperiment,
)
from repository.lib.experiment_templates.mixins.andor_imaging.absorption_imaging import (
    AbsorptionDoubleDipoleTrapMixin,
)
from repository.lib.experiment_templates.mixins.andor_imaging.bg_corrected_andor_image import (
    BGCorrectedAndorImage,
)
from repository.lib.experiment_templates.mixins.andor_imaging.double_trap_imaging import (
    DoubleTrapImagingRepumpedNormalised,
)
from repository.lib.experiment_templates.mixins.andor_imaging.double_trap_imaging import (
    DoubleTrapImagingSpectroscopyRepumpedNormalised,
)
from repository.lib.experiment_templates.mixins.andor_imaging.em_gain import EMGain
from repository.lib.experiment_templates.mixins.andor_imaging.normalised_fast_kinetics import (
    NormalisedDipoleTrapFastKineticsMixin,
)
from repository.lib.experiment_templates.mixins.andor_imaging.normalised_fast_kinetics_base import (
    NormalisedFastKineticsRepumpedMixin,
)
from repository.lib.experiment_templates.mixins.clock_shelving import (
    ClockShelvingAndClearoutDipoleTrapMixin,
)
from repository.lib.experiment_templates.mixins.clock_spectroscopy import (
    ClockRabiSpectroscopyDipoleTrapMixin,
)
from repository.lib.experiment_templates.mixins.clock_spectroscopy import (
    ClockRabiSpectroscopyDownBeamDipoleTrapMixin,
)
from repository.lib.experiment_templates.mixins.doppler_compensation import (
    DopplerCompensationForClockSpecMixin,
)
from repository.lib.experiment_templates.mixins.evaporation_mixin import (
    EvaporationThreeRampsMixin,
)
from repository.lib.experiment_templates.mixins.evaporation_mixin import (
    EvaporationThreeRampsWithFieldRampMixin,
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
from repository.lib.experiment_templates.mixins.painted_quadratic import (
    AdiabaticCoolingWithPaintedQuadraticMixin,
)
from repository.lib.experiment_templates.mixins.painted_quadratic import (
    PaintedMatterwaveLensingMixin,
)
from repository.lib.experiment_templates.mixins.XODT_loading import LoadSingleXODTMixin
from repository.lib.experiment_templates.mixins.XODT_loading import (
    LoadSingleXODTWithPainterMixin,
)
from repository.lib.experiment_templates.mixins.XODT_loading import LoadXXODTMixin
from repository.lib.experiment_templates.mixins.XODT_loading import (
    LoadXXODTWithTransparencyBeamMixin,
)
from repository.lib.experiment_templates.mixins.XODT_molasses import (
    XODTSingleMolassesMixin,
)
from repository.lib.experiment_templates.mixins.XODT_molasses import (
    XODTSingleMolassesPlusDipoleRampMixin,
)

logger = logging.getLogger(__name__)


class SimpleClockSpectroscopyFrag(
    ClockRabiSpectroscopyDipoleTrapMixin,
    BGCorrectedAndorImage,
    DipoleTrapWithExperiment,
):
    """
    SimpleClockSpectroscopy

    As a test, do clock spec with non-normalised imaging
    """


SimpleClockSpectroscopy = make_fragment_scan_exp(SimpleClockSpectroscopyFrag)
