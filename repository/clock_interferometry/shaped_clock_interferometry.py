import logging

from artiq.language import kernel
from ndscan.experiment.entry_point import make_fragment_scan_exp

from repository.lib.experiment_templates.dipole_trap_experiment import (
    DipoleTrapWithExperimentBase,
)
from repository.lib.experiment_templates.mixins.andor_imaging.em_gain import EMGainMixin
from repository.lib.experiment_templates.mixins.andor_imaging.normalised_fast_kinetics import (
    NormalisedDipoleTrapFastKineticsMixin,
)
from repository.lib.experiment_templates.mixins.andor_imaging.normalised_fast_kinetics_base import (
    NormalisedFastKineticsRepumpedMixin,
)
from repository.lib.experiment_templates.mixins.clock_interferometry import (
    ClockInterferometryDipoleTrapMixin,
)
from repository.lib.experiment_templates.mixins.clock_spectroscopy_shaped import (
    ShapedClockShelvingAndClearoutDipoleTrapMixin,
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
    XODTSingleMolassesPlusDipoleRampMixin,
)

logger = logging.getLogger(__name__)


class ClockInterferometryFromSingleXODTEvaporatedShapedSlicingFrag(
    ClockInterferometryDipoleTrapMixin,
    # Imaging
    NormalisedDipoleTrapFastKineticsMixin,  # defines ROI
    NormalisedFastKineticsRepumpedMixin,  # turns on repumps
    EMGainMixin,
    FLIRBlueMOTMeasurementMixin,
    # Loading and state preparation
    LoadSingleXODTMixin,
    XODTSingleMolassesPlusDipoleRampMixin,
    EvaporationThreeRampsMixin,
    OpticalPumpingWithFieldSettingDipoleTrapMixin,
    # Slicing
    ShapedClockShelvingAndClearoutDipoleTrapMixin,
    DipoleTrapWithExperimentBase,
):
    """
    Clock interferometry from dropped single XODT with evaporation, shaped shelving and clearout

    Load into an XODT, velocity-slice using a shaped pulse, then use the up clock beam for spectroscopy, altering the
    (single-pass) AOM.

    Image the ground state atoms, repump and image the excited state, then image
    once more for background.
    """

    @kernel
    def DMA_initialization_checkpoint(self):
        self.DMA_initialization_checkpoint_subfragments()
        self.DMA_initialization_checkpoint_redmot_default()
        self.DMA_initialization_checkpoint_dipole_trap_default()
        self.DMA_initialization_checkpoint_linear_evap()
        self.DMA_initialization_checkpoint_loading_xodt_mot()

    @kernel
    def post_sequence_cleanup_checkpoint(self):
        self.post_sequence_cleanup_checkpoint_subfragments()
        self.post_sequence_cleanup_checkpoint_base()
        self.post_sequence_cleanup_checkpoint_andor()
        self.post_sequence_cleanup_checkpoint_shelving()


ClockInterferometryFromSingleXODTEvaporatedShapedSlicing = make_fragment_scan_exp(
    ClockInterferometryFromSingleXODTEvaporatedShapedSlicingFrag,
    max_rtio_underflow_retries=0,
)
