from ndscan.experiment.entry_point import make_fragment_scan_exp

from repository.lib.experiment_templates.dipole_trap_experiment import (
    DipoleTrapWithExperimentBase,
)
from repository.lib.experiment_templates.mixins.andor_imaging.double_trap_imaging import (
    DoubleTrapImagingClockPulseNormalisedMixin,
)
from repository.lib.experiment_templates.mixins.andor_imaging.em_gain import EMGainMixin
from repository.lib.experiment_templates.mixins.andor_imaging.normalised_fast_kinetics import (
    NormalisedDipoleTrapFastKineticsMixin,
)
from repository.lib.experiment_templates.mixins.andor_imaging.normalised_fast_kinetics_base import (
    NormalisedFastKineticsClockPulseMixin,
)
from repository.lib.experiment_templates.mixins.andor_imaging.single_image_normalised_fast_kinetics import (
    SingleImageNormalisedDoubleTrapRepumpedInterferometryMixin,
)
from repository.lib.experiment_templates.mixins.clock_shelving import (
    ClockShelvingAndClearoutDipoleTrapMixin,
)
from repository.lib.experiment_templates.mixins.doppler_compensation import (
    DopplerCompensationForLMTMixin,
)
from repository.lib.experiment_templates.mixins.evaporation_mixin import (
    FieldOnlyRampInEvapMixin,
)
from repository.lib.experiment_templates.mixins.lmt_interferometry_symmetric_mixin import (
    LMTSymmetricInterferometryMixin,
)
from repository.lib.experiment_templates.mixins.LMT_launch_mixins import (
    LMTInterferometryMixin,
)
from repository.lib.experiment_templates.mixins.LMT_launch_mixins import (
    LMTLaunchDoubleTrapShapedPulseMixin,
)
from repository.lib.experiment_templates.mixins.LMT_launch_mixins import LMTLaunchMixin
from repository.lib.experiment_templates.mixins.LMT_launch_mixins import (
    ShapedFirstPulseLMTInterferometryMixin,
)
from repository.lib.experiment_templates.mixins.optical_pumping import (
    OpticalPumpingWithFieldSettingDipoleTrapMixin,
)
from repository.lib.experiment_templates.mixins.painted_quadratic import (
    AdiabaticCoolingWithPaintedQuadraticMixin,
)
from repository.lib.experiment_templates.mixins.XODT_loading import LoadSingleXODTMixin
from repository.lib.experiment_templates.mixins.XODT_loading import (
    LoadSingleXODTWithPainterMixin,
)
from repository.lib.experiment_templates.mixins.XODT_molasses import (
    XODTSingleMolassesPlusDipoleRampMixin,
)


class LMTInterferometryWithDoubleLaunchSingleImageFrag(
    LMTInterferometryMixin,
    LMTLaunchDoubleTrapShapedPulseMixin,
    SingleImageNormalisedDoubleTrapRepumpedInterferometryMixin,
    EMGainMixin,
    # FLIRBlueMOTMeasurementMixin,
    LoadSingleXODTMixin,
    XODTSingleMolassesPlusDipoleRampMixin,
    OpticalPumpingWithFieldSettingDipoleTrapMixin,
    FieldOnlyRampInEvapMixin,
    ClockShelvingAndClearoutDipoleTrapMixin,
    DopplerCompensationForLMTMixin,
    DipoleTrapWithExperimentBase,
):
    """
    LMT interferometry with double trap launch but using only a single image

    """


class LMTInterferometryWithShapedDoubleLaunchFrag(
    LMTInterferometryMixin,
    DoubleTrapImagingClockPulseNormalisedMixin,
    EMGainMixin,
    # FLIRBlueMOTMeasurementMixin,
    XODTSingleMolassesPlusDipoleRampMixin,
    OpticalPumpingWithFieldSettingDipoleTrapMixin,
    FieldOnlyRampInEvapMixin,
    ClockShelvingAndClearoutDipoleTrapMixin,
    AdiabaticCoolingWithPaintedQuadraticMixin,
    LoadSingleXODTWithPainterMixin,
    LMTLaunchDoubleTrapShapedPulseMixin,
    DopplerCompensationForLMTMixin,
    DipoleTrapWithExperimentBase,
):
    """
    LMT interferometry with double trap launch and shaped first pulse

    """


class LMTInterferometrySymmetricFrag(
    LMTSymmetricInterferometryMixin,
    LMTLaunchMixin,
    NormalisedDipoleTrapFastKineticsMixin,
    NormalisedFastKineticsClockPulseMixin,
    EMGainMixin,
    # FLIRBlueMOTMeasurementMixin,
    XODTSingleMolassesPlusDipoleRampMixin,
    OpticalPumpingWithFieldSettingDipoleTrapMixin,
    FieldOnlyRampInEvapMixin,
    ClockShelvingAndClearoutDipoleTrapMixin,
    AdiabaticCoolingWithPaintedQuadraticMixin,
    LoadSingleXODTWithPainterMixin,
    DopplerCompensationForLMTMixin,
    DipoleTrapWithExperimentBase,
):
    """
    Symmetric LMT interferometry

    """


class LMTInterferometryWithLaunchFrag(
    LMTInterferometryMixin,
    LMTLaunchMixin,
    NormalisedDipoleTrapFastKineticsMixin,
    NormalisedFastKineticsClockPulseMixin,
    EMGainMixin,
    # FLIRBlueMOTMeasurementMixin,
    LoadSingleXODTMixin,
    XODTSingleMolassesPlusDipoleRampMixin,
    OpticalPumpingWithFieldSettingDipoleTrapMixin,
    FieldOnlyRampInEvapMixin,
    ClockShelvingAndClearoutDipoleTrapMixin,
    DopplerCompensationForLMTMixin,
    DipoleTrapWithExperimentBase,
):
    """
    LMT interferometry with launch

    """


class ShapedFirstPulseLMTInterferometryFrag(
    ShapedFirstPulseLMTInterferometryMixin,
    LMTLaunchMixin,
    NormalisedDipoleTrapFastKineticsMixin,
    NormalisedFastKineticsClockPulseMixin,
    EMGainMixin,
    # FLIRBlueMOTMeasurementMixin,
    LoadSingleXODTMixin,
    XODTSingleMolassesPlusDipoleRampMixin,
    OpticalPumpingWithFieldSettingDipoleTrapMixin,
    FieldOnlyRampInEvapMixin,
    ClockShelvingAndClearoutDipoleTrapMixin,
    DopplerCompensationForLMTMixin,
    DipoleTrapWithExperimentBase,
):
    """
    LMT interferometry with shaped selective pulses

    """


TInterferometryWithLaunch = make_fragment_scan_exp(LMTInterferometryWithLaunchFrag)
ShapedFirstPulseLMTInterferometry = make_fragment_scan_exp(
    ShapedFirstPulseLMTInterferometryFrag, max_rtio_underflow_retries=0
)

LMTInterferometryWithDoubleLaunchSingleImage = make_fragment_scan_exp(
    LMTInterferometryWithDoubleLaunchSingleImageFrag
)

LMTInterferometryWithShapedDoubleLaunch = make_fragment_scan_exp(
    LMTInterferometryWithShapedDoubleLaunchFrag, max_rtio_underflow_retries=0
)

LMTInterferometrySymmetric = make_fragment_scan_exp(LMTInterferometrySymmetricFrag)

LMTInterferometrySymmetric = make_fragment_scan_exp(LMTInterferometrySymmetricFrag)
