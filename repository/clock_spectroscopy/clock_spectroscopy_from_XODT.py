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
    DoubleTrapImagingNormalised,
)
from repository.lib.experiment_templates.mixins.andor_imaging.em_gain import EMGain
from repository.lib.experiment_templates.mixins.andor_imaging.normalised_fast_kinetics import (
    NormalisedDipoleTrapFastKineticsMixin,
)
from repository.lib.experiment_templates.mixins.clock_shelving import (
    ClockShelvingAndClearoutDipoleTrapMixin,
)
from repository.lib.experiment_templates.mixins.clock_spectroscopy import (
    ClockRabiSpectroscopyDipoleTrapMixin,
)
from repository.lib.experiment_templates.mixins.evaporation_mixin import (
    EvaporationThreeRampsMixin,
)
from repository.lib.experiment_templates.mixins.flir_blue_mot_measurement import (
    FLIRBlueMOTMeasurementMixin,
)
from repository.lib.experiment_templates.mixins.optical_pumping import (
    OpticalPumpingWithFieldSettingDipoleTrapMixin,
)
from repository.lib.experiment_templates.mixins.XODT_loading import LoadSingleXODTMixin
from repository.lib.experiment_templates.mixins.XODT_molasses import (
    XODTSingleMolassesPlusFieldRampMixin,
    XODTSingleMolassesMixin,
)

logger = logging.getLogger(__name__)


class ClockSpecFromSingleXODTFrag(
    ClockRabiSpectroscopyDipoleTrapMixin,
    NormalisedDipoleTrapFastKineticsMixin,
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

    @kernel
    def before_start_hook(self):
        self.before_start_hook_clockspec()


class ClockSpecFromSingleXODTEvaporatedFrag(
    ClockRabiSpectroscopyDipoleTrapMixin,
    NormalisedDipoleTrapFastKineticsMixin,
    EMGain,
    FLIRBlueMOTMeasurementMixin,
    LoadSingleXODTMixin,
    XODTSingleMolassesMixin,
    EvaporationThreeRampsMixin,
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
        self.DMA_initialization_hook_linear_evap()
        self.DMA_initialization_hook_loading_xodt_mot()

    @kernel
    def before_start_hook(self):
        self.before_start_hook_clockspec()


class ClockSpecFromXXODTFrag(
    ClockRabiSpectroscopyDipoleTrapMixin,
    DoubleTrapImagingNormalised,
    EMGain,
    FLIRBlueMOTMeasurementMixin,
    XODTSingleMolassesPlusFieldRampMixin,
    OpticalPumpingWithFieldSettingDipoleTrapMixin,
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
    def before_start_hook(self):
        self.before_start_hook_clockspec()


class ClockSpecFromXXODTWithShelvingAndClearoutFrag(
    ClockRabiSpectroscopyDipoleTrapMixin,
    ClockShelvingAndClearoutDipoleTrapMixin,
    DoubleTrapImagingNormalised,
    EMGain,
    FLIRBlueMOTMeasurementMixin,
    XODTSingleMolassesPlusFieldRampMixin,
    OpticalPumpingWithFieldSettingDipoleTrapMixin,
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
    def before_start_hook(self):
        self.before_start_hook_clockspec()


class AbsImagingFromXXODTWithShelvingAndClearoutFrag(
    ClockRabiSpectroscopyDipoleTrapMixin,
    ClockShelvingAndClearoutDipoleTrapMixin,
    FLIRBlueMOTMeasurementMixin,
    XODTSingleMolassesPlusFieldRampMixin,
    OpticalPumpingWithFieldSettingDipoleTrapMixin,
    DipoleTrapWithExperiment,
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
    def before_start_hook(self):
        self.before_start_hook_clockspec()


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
