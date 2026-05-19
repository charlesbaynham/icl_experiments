import logging

from artiq.language import kernel
from ndscan.experiment.entry_point import make_fragment_scan_exp
from pyaion.fragments.default_beam_setter import SetBeamsToDefaults
from pyaion.fragments.default_beam_setter import make_set_beams_to_default

from repository.lib import constants
from repository.lib.experiment_templates.mixins.andor_imaging.absorption_imaging import (
    AbsorptionDipoleTrapMixin,
)
from repository.lib.experiment_templates.mixins.andor_imaging.bg_corrected_andor_image import (
    BGCorrectedAndorImageSingleXODT,
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
from repository.lib.experiment_templates.mixins.evaporation_mixin import (
    FieldOnlyRampInEvapMixin,
)
from repository.lib.experiment_templates.mixins.flir_measurement import (
    FLIRMeasurementMixin,
)
from repository.lib.experiment_templates.mixins.optical_pumping import (
    OpticalPumpingWithFieldSettingDipoleTrapMixin,
)
from repository.lib.experiment_templates.mixins.painted_quadratic import (
    AdiabaticCoolingWithPaintedQuadraticMixin,
)
from repository.lib.experiment_templates.mixins.painted_quadratic import (
    MatterwaveLensingVerticalBeam,
)
from repository.lib.experiment_templates.mixins.XODT_loading import LoadSingleXODTMixin
from repository.lib.experiment_templates.mixins.XODT_loading import (
    LoadSingleXODTWithPainterMixin,
)
from repository.lib.experiment_templates.mixins.XODT_molasses import (
    XODTSingleMolassesPlusDipoleRampMixin,
)

logger = logging.getLogger(__name__)


class MeasureSingleXODTBGCorrectedFrag(
    FLIRMeasurementMixin,
    BGCorrectedAndorImageSingleXODT,
    LoadSingleXODTMixin,
):
    """
    Make Single XODT and image twice for BG subtraction
    """

    def build_fragment(self):
        logger.warning("The transparency beam is being turned on for debugging")
        self.setattr_fragment(
            "transparency_setter",
            make_set_beams_to_default(
                suservo_beam_infos=[
                    constants.SUSERVOED_BEAMS["blue_transparency_beam"]
                ],
                use_automatic_setup=True,
                use_automatic_turnon=True,
            ),
        )
        self.transparency_setter: SetBeamsToDefaults
        super().build_fragment()

    @kernel
    def DMA_initialization_hook(self):
        self.DMA_initialization_hook_default()
        self.DMA_initialization_hook_loading_xodt_mot()

    @kernel
    def do_experiment_after_dipole_trap_hook(self):
        pass


class MeasureSingleXODTAbsFrag(
    AbsorptionDipoleTrapMixin,
    LoadSingleXODTMixin,
):
    """
    Measure a single XODT with absorption imaging
    """

    @kernel
    def DMA_initialization_hook(self):
        self.DMA_initialization_hook_default()
        self.DMA_initialization_hook_loading_xodt_mot()

    @kernel
    def do_experiment_after_dipole_trap_hook(self):
        pass


class MeasureCooledXODTFrag(
    FLIRMeasurementMixin,
    NormalisedDipoleTrapFastKineticsMixin,
    NormalisedFastKineticsRepumpedMixin,
    XODTSingleMolassesPlusDipoleRampMixin,
    OpticalPumpingWithFieldSettingDipoleTrapMixin,
    FieldOnlyRampInEvapMixin,
    MatterwaveLensingVerticalBeam,
    AdiabaticCoolingWithPaintedQuadraticMixin,
    LoadSingleXODTWithPainterMixin,
    ClockShelvingAndClearoutDipoleTrapMixin,
    EMGain,
):
    """
    Measure a Single XODT with adiabatic cooling and delta kick
    """

    @kernel
    def DMA_initialization_hook(self):
        self.DMA_initialization_hook_default()
        self.DMA_initialization_hook_adiabatic_cooling()
        self.DMA_initialization_hook_painter_on()
        self.DMA_initialization_hook_evap_with_field_ramp()
        self.DMA_initialization_hook_loading_xodt_mot()
        self.DMA_initialization_hook_xodt_molasses()

    @kernel
    def post_sequence_cleanup_hook(self):
        self.post_narrowband_hook_default()
        self.post_sequence_cleanup_hook_andor()
        self.post_sequence_cleanup_hook_loading()

    @kernel
    def do_experiment_after_dipole_trap_hook(self):
        pass


MeasureSingleXODTBGCorrected = make_fragment_scan_exp(MeasureSingleXODTBGCorrectedFrag)
MeasureSingleXODTAbs = make_fragment_scan_exp(MeasureSingleXODTAbsFrag)
MeasureCooledXODT = make_fragment_scan_exp(MeasureCooledXODTFrag)
