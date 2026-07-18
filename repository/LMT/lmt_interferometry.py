from artiq.language import kernel
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
    NormalisedFastKineticsRepumpedMixin,
)
from repository.lib.experiment_templates.mixins.andor_imaging.single_image_normalised_fast_kinetics import (
    SingleImageNormalisedDoubleTrapClockPulseInterferometryMixin,
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
    SingleImageNormalisedDoubleTrapClockPulseInterferometryMixin,
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
    LMT interferometry with double trap launch but using only a single image

    """

    @kernel
    def DMA_initialization_hook(self):
        self.DMA_initialization_hook_redmot_default()
        self.DMA_initialization_hook_dipole_trap_default()
        self.DMA_initialization_hook_loading_xodt_mot()
        self.DMA_initialization_hook_xodt_molasses()
        self.DMA_initialization_hook_evap_with_field_ramp()
        self.DMA_initialization_hook_painter_on()
        self.DMA_initialization_hook_adiabatic_cooling()

    @kernel
    def post_sequence_cleanup_hook(self):
        self.post_sequence_cleanup_hook_base()
        self.post_sequence_cleanup_hook_andor()
        self.post_sequence_cleanup_hook_shelving()
        self.post_sequence_cleanup_hook_lmt()
        self.post_sequence_cleanup_hook_loading()


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

    @kernel
    def DMA_initialization_hook(self):
        self.DMA_initialization_hook_redmot_default()
        self.DMA_initialization_hook_dipole_trap_default()
        self.DMA_initialization_hook_loading_xodt_mot()
        self.DMA_initialization_hook_xodt_molasses()
        self.DMA_initialization_hook_painter_on()
        self.DMA_initialization_hook_adiabatic_cooling()
        self.DMA_initialization_hook_evap_with_field_ramp()

    @kernel
    def post_sequence_cleanup_hook(self):
        self.post_sequence_cleanup_hook_base()
        self.post_sequence_cleanup_hook_andor()
        self.post_sequence_cleanup_hook_shelving()
        self.post_sequence_cleanup_hook_loading()
        self.post_sequence_cleanup_hook_lmt()


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

    @kernel
    def DMA_initialization_hook(self):
        self.DMA_initialization_hook_redmot_default()
        self.DMA_initialization_hook_dipole_trap_default()
        self.DMA_initialization_hook_loading_xodt_mot()
        self.DMA_initialization_hook_xodt_molasses()
        self.DMA_initialization_hook_painter_on()
        self.DMA_initialization_hook_adiabatic_cooling()
        self.DMA_initialization_hook_evap_with_field_ramp()

    @kernel
    def post_sequence_cleanup_hook(self):
        self.post_sequence_cleanup_hook_base()
        self.post_sequence_cleanup_hook_andor()
        self.post_sequence_cleanup_hook_shelving()
        self.post_sequence_cleanup_hook_lmt()
        self.post_sequence_cleanup_hook_loading()


class LMTInterferometryWithLaunchFrag(
    LMTInterferometryMixin,
    LMTLaunchMixin,
    NormalisedDipoleTrapFastKineticsMixin,
    NormalisedFastKineticsClockPulseMixin,
    EMGainMixin,
    # FLIRBlueMOTMeasurementMixin,
    AdiabaticCoolingWithPaintedQuadraticMixin,
    LoadSingleXODTWithPainterMixin,
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

    @kernel
    def DMA_initialization_hook(self):
        self.DMA_initialization_hook_redmot_default()
        self.DMA_initialization_hook_dipole_trap_default()
        self.DMA_initialization_hook_loading_xodt_mot()
        self.DMA_initialization_hook_xodt_molasses()
        self.DMA_initialization_hook_evap_with_field_ramp()
        self.DMA_initialization_hook_painter_on()
        self.DMA_initialization_hook_adiabatic_cooling()

    @kernel
    def post_sequence_cleanup_hook(self):
        self.post_sequence_cleanup_hook_base()
        self.post_sequence_cleanup_hook_andor()
        self.post_sequence_cleanup_hook_shelving()
        self.post_sequence_cleanup_hook_lmt()
        self.post_sequence_cleanup_hook_loading()


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

    @kernel
    def DMA_initialization_hook(self):
        self.DMA_initialization_hook_redmot_default()
        self.DMA_initialization_hook_dipole_trap_default()
        self.DMA_initialization_hook_loading_xodt_mot()
        self.DMA_initialization_hook_xodt_molasses()
        self.DMA_initialization_hook_evap_with_field_ramp()

    @kernel
    def post_sequence_cleanup_hook(self):
        self.post_sequence_cleanup_hook_base()
        self.post_sequence_cleanup_hook_andor()
        self.post_sequence_cleanup_hook_shelving()


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
