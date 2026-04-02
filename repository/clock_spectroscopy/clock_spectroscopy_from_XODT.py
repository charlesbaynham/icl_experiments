import logging

from artiq.language import kernel
from ndscan.experiment.entry_point import make_fragment_scan_exp

from repository.lib.experiment_templates.dipole_trap_experiment import (
    DipoleTrapWithExperiment,
)
from repository.lib.experiment_templates.mixins.andor_imaging.absorption_imaging import (
    AbsorptionDoubleDipoleTrapMixin,
)
from repository.lib.experiment_templates.mixins.andor_imaging.double_trap_imaging import (
    DoubleTrapImagingRepumpedNormalised,
)
from repository.lib.experiment_templates.mixins.andor_imaging.double_trap_imaging import (
    DoubleTrapImagingSpectroscopyRepumpedNormalised,
)
from repository.lib.experiment_templates.mixins.andor_imaging.em_gain import EMGain
from repository.lib.experiment_templates.mixins.andor_imaging.single_fast_kinetics import (
    SingleImageNormalisedDipoleTrapFastKineticsMixin,
)
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
from repository.lib.experiment_templates.mixins.XODT_loading import LoadSingleXODTMixin
from repository.lib.experiment_templates.mixins.XODT_loading import LoadXXODTMixin
from repository.lib.experiment_templates.mixins.XODT_loading import (
    LoadXXODTWithTransparencyBeamMixin,
)
from repository.lib.experiment_templates.mixins.XODT_molasses import (
    XODTSingleMolassesPlusDipoleRampMixin,
)

logger = logging.getLogger(__name__)


class ClockSpecFromSingleXODTFrag(
    ClockRabiSpectroscopyDipoleTrapMixin,
    NormalisedDipoleTrapFastKineticsMixin,
    NormalisedFastKineticsRepumpedMixin,
    EMGain,
    FLIRBlueMOTMeasurementMixin,
    LoadSingleXODTMixin,
    OpticalPumpingWithFieldSettingDipoleTrapMixin,
    DipoleTrapWithExperiment,
):
    """
    Clock spectroscopy from dropped single XODT

    Load into an XODT, then use the up clock beam for spectroscopy, altering the
    (single-pass) AOM.

    Image the ground state atoms, repump and image the excited state, then image
    once more for background.
    """

    @kernel
    def DMA_initialization_hook(self):
        self.DMA_initialization_hook_default()
        self.DMA_initialization_hook_loading_xodt_mot()


class ClockSpecFromSingleXODTEvaporatedFrag(
    ClockRabiSpectroscopyDipoleTrapMixin,
    NormalisedDipoleTrapFastKineticsMixin,
    NormalisedFastKineticsRepumpedMixin,
    EMGain,
    FLIRBlueMOTMeasurementMixin,
    LoadSingleXODTMixin,
    XODTSingleMolassesPlusDipoleRampMixin,
    EvaporationThreeRampsWithFieldRampMixin,
    OpticalPumpingWithFieldSettingDipoleTrapMixin,
    DipoleTrapWithExperiment,
):
    """
    Clock spectroscopy from dropped single XODT with evaporation

    Load into an XODT, then use the up clock beam for spectroscopy, altering the
    (single-pass) AOM.

    Image the ground state atoms, repump and image the excited state, then image
    once more for background.
    """

    @kernel
    def DMA_initialization_hook(self):
        self.DMA_initialization_hook_default()
        self.DMA_initialization_hook_evap_with_field_ramp()
        self.DMA_initialization_hook_loading_xodt_mot()


class ClockSpecFromSingleXODTEvaporatedShelvingFrag(
    ClockRabiSpectroscopyDipoleTrapMixin,
    # DopplerCompensationForClockSpecMixin,
    NormalisedDipoleTrapFastKineticsMixin,  # defines ROI
    NormalisedFastKineticsRepumpedMixin,  # turns on repumps
    EMGain,
    FLIRBlueMOTMeasurementMixin,
    LoadSingleXODTMixin,
    XODTSingleMolassesPlusDipoleRampMixin,
    # XODTRetroedMolassesPlusDipoleRampMixin,
    EvaporationThreeRampsWithFieldRampMixin,
    OpticalPumpingWithFieldSettingDipoleTrapMixin,
    ClockShelvingAndClearoutDipoleTrapMixin,
    DipoleTrapWithExperiment,
):
    """
    Clock spectroscopy from dropped single XODT with evaporation, shelving and clearout

    Load into an XODT, then use the up clock beam for spectroscopy, altering the
    (single-pass) AOM.

    Image the ground state atoms, repump and image the excited state, then image
    once more for background.
    """

    @kernel
    def DMA_initialization_hook(self):
        self.DMA_initialization_hook_default()
        self.DMA_initialization_hook_evap_with_field_ramp()
        self.DMA_initialization_hook_loading_xodt_mot()

    @kernel
    def post_sequence_cleanup_hook(self):
        self.post_sequence_cleanup_hook_base()
        self.post_sequence_cleanup_hook_andor()
        self.post_sequence_cleanup_hook_shelving()


class ClockSpecDownFromSingleXODTEvaporatedShelvingFrag(
    ClockRabiSpectroscopyDownBeamDipoleTrapMixin,
    # DopplerCompensationForClockSpecMixin,
    NormalisedDipoleTrapFastKineticsMixin,  # defines ROI
    NormalisedFastKineticsRepumpedMixin,  # turns on repumps
    EMGain,
    FLIRBlueMOTMeasurementMixin,
    LoadSingleXODTMixin,
    XODTSingleMolassesPlusDipoleRampMixin,
    EvaporationThreeRampsWithFieldRampMixin,
    OpticalPumpingWithFieldSettingDipoleTrapMixin,
    ClockShelvingAndClearoutDipoleTrapMixin,
    DipoleTrapWithExperiment,
):
    """
    Down beam clock spectroscopy from dropped single XODT with evaporation, shelving and clearout

    Load into an XODT, then use the up clock beam for spectroscopy, altering the
    (single-pass) AOM.

    Image the ground state atoms, repump and image the excited state, then image
    once more for background.
    """

    @kernel
    def DMA_initialization_hook(self):
        self.DMA_initialization_hook_default()
        self.DMA_initialization_hook_evap_with_field_ramp()
        self.DMA_initialization_hook_loading_xodt_mot()

    @kernel
    def post_sequence_cleanup_hook(self):
        self.post_sequence_cleanup_hook_base()
        self.post_sequence_cleanup_hook_andor()
        self.post_sequence_cleanup_hook_shelving()


class ClockSpecFromXXODTFrag(
    # Clock spec:
    ClockRabiSpectroscopyDipoleTrapMixin,
    # Spin polarisation:
    OpticalPumpingWithFieldSettingDipoleTrapMixin,
    FieldOnlyRampInEvapMixin,
    # Imaging:
    DoubleTrapImagingRepumpedNormalised,
    EMGain,
    FLIRBlueMOTMeasurementMixin,
    # Loading:
    LoadXXODTWithTransparencyBeamMixin,
    # Base:
    DipoleTrapWithExperiment,
):
    """
    Clock spectroscopy from dropped XXODT

    Load into an XXODT, then use the up clock beam for spectroscopy, altering the
    (single-pass) AOM.

    Image the ground state atoms, repump and image the excited state, then image
    once more for background.
    """

    @kernel
    def DMA_initialization_hook(self):
        self.DMA_initialization_hook_default()
        self.DMA_initialization_hook_loading_xodt_mot()
        self.DMA_initialization_hook_evap_with_field_ramp()


class ClockSpecFromXXODTWithShelvingAndClearoutFrag(
    # Clock spec:
    ClockRabiSpectroscopyDipoleTrapMixin,
    DopplerCompensationForClockSpecMixin,
    # Spin polarisation:
    OpticalPumpingWithFieldSettingDipoleTrapMixin,
    FieldOnlyRampInEvapMixin,
    # Shelving and clearout:
    ClockShelvingAndClearoutDipoleTrapMixin,
    # Imaging:
    DoubleTrapImagingSpectroscopyRepumpedNormalised,
    EMGain,
    FLIRBlueMOTMeasurementMixin,
    # Loading:
    LoadXXODTWithTransparencyBeamMixin,
    # Base:
    DipoleTrapWithExperiment,
):
    """
    Clock spectroscopy from dropped XXODT with shelving and clearout

    Load into an XXODT, then use the up clock beam for spectroscopy, altering the
    (single-pass) AOM.

    Image the ground state atoms, repump and image the excited state, then image
    once more for background.
    """

    @kernel
    def DMA_initialization_hook(self):
        self.DMA_initialization_hook_default()
        self.DMA_initialization_hook_loading_xodt_mot()
        self.DMA_initialization_hook_evap_with_field_ramp()

    @kernel
    def post_sequence_cleanup_hook(self):
        self.post_sequence_cleanup_hook_base()
        self.post_sequence_cleanup_hook_andor()
        self.post_sequence_cleanup_hook_shelving()


class AbsImagingFromXXODTWithShelvingAndClearoutFrag(
    # Clock spec:
    ClockRabiSpectroscopyDipoleTrapMixin,
    DopplerCompensationForClockSpecMixin,
    # Spin polarisation:
    OpticalPumpingWithFieldSettingDipoleTrapMixin,
    FieldOnlyRampInEvapMixin,
    # Shelving and clearout:
    ClockShelvingAndClearoutDipoleTrapMixin,
    # Loading:
    LoadXXODTMixin,
    # Base:
    AbsorptionDoubleDipoleTrapMixin,
):
    """
    Clock spectroscopy from dropped XXODT with shelving, clearout, and absorption imaging

    Load into an XXODT, then use the up clock beam for spectroscopy, altering the
    (single-pass) AOM.

    Image the ground state atoms, repump and image the excited state, then image
    once more for background.
    """

    @kernel
    def DMA_initialization_hook(self):
        self.DMA_initialization_hook_default()
        self.DMA_initialization_hook_loading_xodt_mot()
        self.DMA_initialization_hook_evap_with_field_ramp()

    @kernel
    def post_sequence_cleanup_hook(self):
        self.post_sequence_cleanup_hook_base()
        self.post_sequence_cleanup_hook_andor()
        self.post_sequence_cleanup_hook_shelving()


class ClockSpecFromSingleXODTSingleImageFrag(
    ClockRabiSpectroscopyDipoleTrapMixin,
    SingleImageNormalisedDipoleTrapFastKineticsMixin,
    NormalisedFastKineticsRepumpedMixin,
    EMGain,
    FLIRBlueMOTMeasurementMixin,
    LoadSingleXODTMixin,
    OpticalPumpingWithFieldSettingDipoleTrapMixin,
    DipoleTrapWithExperiment,
):
    """
    Clock spectroscopy from dropped single XODT

    Load into an XODT, then use the up clock beam for spectroscopy, altering the
    (single-pass) AOM.

    Image the ground state atoms, repump and image the excited state, then image
    once more for background.
    """

    @kernel
    def DMA_initialization_hook(self):
        self.DMA_initialization_hook_default()
        self.DMA_initialization_hook_loading_xodt_mot()


ClockSpecFromSingleXODTSingleImage = make_fragment_scan_exp(
    ClockSpecFromSingleXODTSingleImageFrag
)

AbsImagingFromXXODTWithShelvingAndClearout = make_fragment_scan_exp(
    AbsImagingFromXXODTWithShelvingAndClearoutFrag
)

ClockSpecFromXXODT = make_fragment_scan_exp(ClockSpecFromXXODTFrag)
ClockSpecFromSingleXODTEvaporated = make_fragment_scan_exp(
    ClockSpecFromSingleXODTEvaporatedFrag
)
ClockSpecFromXXODTWithShelving = make_fragment_scan_exp(
    ClockSpecFromXXODTWithShelvingAndClearoutFrag
)
ClockSpecFromXODT = make_fragment_scan_exp(ClockSpecFromSingleXODTFrag)
ClockSpecFromSingleXODTEvaporatedShelving = make_fragment_scan_exp(
    ClockSpecFromSingleXODTEvaporatedShelvingFrag
)
ClockSpecDownFromSingleXODTEvaporatedShelving = make_fragment_scan_exp(
    ClockSpecDownFromSingleXODTEvaporatedShelvingFrag
)
