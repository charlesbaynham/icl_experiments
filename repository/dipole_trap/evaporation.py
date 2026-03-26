import logging

from artiq.language import kernel
from ndscan.experiment.entry_point import make_fragment_scan_exp

from repository.lib.experiment_templates.mixins.andor_imaging.absorption_imaging import (
    AbsorptionDipoleTrapMixin,
)
from repository.lib.experiment_templates.mixins.andor_imaging.bg_corrected_andor_image import (
    BGCorrectedAndorImageSingleXODT,
)
from repository.lib.experiment_templates.mixins.evaporation_mixin import (
    EvaporationThreeRampsMixin,
)
from repository.lib.experiment_templates.mixins.flir_measurement import (
    FLIRMeasurementMixin,
)
from repository.lib.experiment_templates.mixins.optical_pumping import (
    OpticalPumpingWithFieldSettingDipoleTrapMixin,
)
from repository.lib.experiment_templates.mixins.XODT_loading import LoadSingleXODTMixin
from repository.lib.experiment_templates.mixins.XODT_molasses import (
    XODTRetroedMolassesPlusDipoleRampMixin,
)
from repository.lib.experiment_templates.mixins.XODT_molasses import (
    XODTSingleMolassesPlusDipoleRampMixin,
)

logger = logging.getLogger(__name__)


class MeasureEvaporatedXODTFrag(
    FLIRMeasurementMixin,
    BGCorrectedAndorImageSingleXODT,
    LoadSingleXODTMixin,
    XODTSingleMolassesPlusDipoleRampMixin,
    EvaporationThreeRampsMixin,
    OpticalPumpingWithFieldSettingDipoleTrapMixin,
    # ClearOut689Mixin,
):
    """
    Measure a Single XODT with evaporation
    """

    @kernel
    def DMA_initialization_hook(self):
        self.DMA_initialization_hook_default()
        self.DMA_initialization_hook_linear_evap()
        self.DMA_initialization_hook_loading_xodt_mot()
        self.DMA_initialization_hook_xodt_molasses()

    @kernel
    def do_experiment_after_dipole_trap_hook(self):
        pass


class MeasureXODTNewMolassesFrag(
    FLIRMeasurementMixin,
    BGCorrectedAndorImageSingleXODT,
    LoadSingleXODTMixin,
    XODTRetroedMolassesPlusDipoleRampMixin,
):
    """
    Measure a Single XODT with retroed molasses
    """

    @kernel
    def DMA_initialization_hook(self):
        self.DMA_initialization_hook_default()
        self.DMA_initialization_hook_loading_xodt_mot()
        self.DMA_initialization_hook_xodt_molasses()

    @kernel
    def do_experiment_after_dipole_trap_hook(self):
        pass


class MeasureExaporatedXODTAbsFrag(
    AbsorptionDipoleTrapMixin,
    LoadSingleXODTMixin,
    XODTSingleMolassesPlusDipoleRampMixin,
    EvaporationThreeRampsMixin,
    OpticalPumpingWithFieldSettingDipoleTrapMixin,
):
    """
    Measure a single XODT with evaporation & absorption imaging
    """

    @kernel
    def DMA_initialization_hook(self):
        self.DMA_initialization_hook_default()
        self.DMA_initialization_hook_linear_evap()
        self.DMA_initialization_hook_loading_xodt_mot()
        self.DMA_initialization_hook_xodt_molasses()

    @kernel
    def do_experiment_after_dipole_trap_hook(self):
        pass


MeasureEvaporatedXODT = make_fragment_scan_exp(MeasureEvaporatedXODTFrag)
MeasureExaporatedXODTAbs = make_fragment_scan_exp(MeasureExaporatedXODTAbsFrag)
MeasureXODTNewMolasses = make_fragment_scan_exp(MeasureXODTNewMolassesFrag)
