import logging

from artiq.language import kernel
from ndscan.experiment.entry_point import make_fragment_scan_exp

from repository.lib.experiment_templates.dipole_trap_experiment import (
    DipoleTrapWithExperiment,
)
from repository.lib.experiment_templates.mixins.andor_imaging.em_gain import EMGain
from repository.lib.experiment_templates.mixins.andor_imaging.single_fast_kinetics import (
    SingleImageNormalisedDipoleTrapFastKineticsMixin,
)
from repository.lib.experiment_templates.mixins.andor_imaging.single_fast_kinetics import (
    SingleImageNormalisedFastKineticsRepumpedMixin,
)
from repository.lib.experiment_templates.mixins.clock_spectroscopy import (
    ClockRabiSpectroscopyDipoleTrapMixin,
)
from repository.lib.experiment_templates.mixins.flir_blue_mot_measurement import (
    FLIRBlueMOTMeasurementMixin,
)
from repository.lib.experiment_templates.mixins.optical_pumping import (
    OpticalPumpingWithFieldSettingDipoleTrapMixin,
)
from repository.lib.experiment_templates.mixins.XODT_loading import LoadSingleXODTMixin

logger = logging.getLogger(__name__)


class ClockSpecFromSingleXODTShelvingSingleImageFrag(
    ClockRabiSpectroscopyDipoleTrapMixin,
    SingleImageNormalisedDipoleTrapFastKineticsMixin,
    SingleImageNormalisedFastKineticsRepumpedMixin,
    EMGain,
    FLIRBlueMOTMeasurementMixin,
    LoadSingleXODTMixin,
    OpticalPumpingWithFieldSettingDipoleTrapMixin,
    DipoleTrapWithExperiment,
):
    """
    Clock spectroscopy with shelving and clearout from dropped single XODT using only a single image

    Load into an XODT, then use the up clock beam for spectroscopy, altering the
    (single-pass) AOM.

    Image the ground state atoms, repump and image the excited state, then image
    once more for background.
    """

    @kernel
    def DMA_initialization_hook(self):
        self.DMA_initialization_hook_default()
        self.DMA_initialization_hook_loading_xodt_mot()


ClockSpecFromSingleXODTShelvingSingleImage = make_fragment_scan_exp(
    ClockSpecFromSingleXODTShelvingSingleImageFrag
)
