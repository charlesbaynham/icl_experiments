import logging

from artiq.experiment import kernel
from ndscan.experiment.entry_point import make_fragment_scan_exp

from repository.lib.experiment_templates.dipole_trap_experiment import (
    DipoleTrapWithExperiment,
)
from repository.lib.experiment_templates.mixins.andor_imaging.em_gain import EMGain
from repository.lib.experiment_templates.mixins.andor_imaging.normalised_fast_kinetics import (
    NormalisedDipoleTrapFastKineticsMixin,
)
from repository.lib.experiment_templates.mixins.clock_spectroscopy_shaped import (
    ShapedRabiSpectroscopyDipoleTrapMixin,
)
from repository.lib.experiment_templates.mixins.flir_blue_mot_measurement import (
    FLIRBlueMOTMeasurementMixin,
)
from repository.lib.experiment_templates.mixins.pumped_lattice import (
    OpticalPumpingWithFieldSettingDipoleTrapMixin,
)
from repository.lib.experiment_templates.mixins.XODT_loading import LoadSingleXODTMixin

logger = logging.getLogger(__name__)


class ShapedClockSpecFromSingleXODTFrag(
    ShapedRabiSpectroscopyDipoleTrapMixin,
    NormalisedDipoleTrapFastKineticsMixin,
    EMGain,
    FLIRBlueMOTMeasurementMixin,
    LoadSingleXODTMixin,
    OpticalPumpingWithFieldSettingDipoleTrapMixin,
    DipoleTrapWithExperiment,
):
    """
    Shaped clock spectroscopy from dropped single XODT with evaporation

    Load into an XODT, then use the up clock beam for spectroscopy, altering the
    (single-pass) SUServo AOM's frequency and shaping the pulse with the final
    switch AOM.

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


ShapedClockSpecFromSingleXODT = make_fragment_scan_exp(
    ShapedClockSpecFromSingleXODTFrag, max_rtio_underflow_retries=0
)
