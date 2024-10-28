import logging

from artiq.experiment import kernel
from ndscan.experiment.entry_point import make_fragment_scan_exp

from repository.lib import constants
from repository.lib.experiment_templates.mixins.andor_imaging.bg_corrected_andor_image import (
    BGCorrectedAndorImage,
)
from repository.lib.experiment_templates.mixins.andor_imaging.double_trap_imaging import (
    DoubleTrapImagingBasic,
)
from repository.lib.experiment_templates.mixins.andor_imaging.double_trap_imaging import (
    DoubleTrapImagingNormalised,
)

from repository.lib.experiment_templates.mixins.andor_imaging.double_trap_imaging import (
    DoubleTrapImagingBGSubtracted,
)
from repository.lib.experiment_templates.mixins.flir_measurement import (
    FLIRMeasurementMixin,
)
from repository.lib.experiment_templates.mixins.ndscan_analysis_exponential_decay import (
    ExponentialDecayMixin,
)
from repository.lib.experiment_templates.mixins.XODT_molasses import XODTMolassesMixin

logger = logging.getLogger(__name__)

EXPOSE_MOLASSES_1_PARAMS = False
EXPOSE_MOLASSES_2_PARAMS = True


class _MeasureDipoleTrapBase(
    FLIRMeasurementMixin,
    ExponentialDecayMixin,
    XODTMolassesMixin,
):
    """
    Load a dipole trap, do 689 nm molasses, hold, and take BG subtracted image
    """

    def build_fragment(self):
        super().build_fragment()

        # Expose the molasses ramp parameters if desired
        if EXPOSE_MOLASSES_1_PARAMS:
            names = [
                n
                for n in self.molasses_xodt_1._free_params.keys()
                if "suservo" not in n
            ]
            for name in names:
                self.setattr_param_rebind(
                    f"molasses_1_{name}", self.molasses_xodt_1, original_name=name
                )
        if EXPOSE_MOLASSES_2_PARAMS:
            names = [n for n in self.molasses_xodt_2._free_params.keys()]
            for name in names:
                self.setattr_param_rebind(
                    f"molasses_2_{name}", self.molasses_xodt_2, original_name=name
                )

    @kernel
    def DMA_initialization_hook(self):
        self.DMA_initialization_hook_default()
        self.DMA_initialization_hook_xodt_molasses()

    @kernel
    def do_experiment_after_dipole_trap_hook(self):
        # Release the atoms for time of flight measurement
        self.dipole_beam_controller.turn_off_dipole_beams()


class MeasureDipoleTrapFrag(BGCorrectedAndorImage, _MeasureDipoleTrapBase):
    def build_fragment(self):
        super().build_fragment()

        self.setattr_param_rebind(
            "roi_0_x0",
            self.andor_camera_control,
        )
        self.setattr_param_rebind(
            "roi_0_x1",
            self.andor_camera_control,
        )
        self.setattr_param_rebind(
            "roi_0_y0",
            self.andor_camera_control,
        )
        self.setattr_param_rebind(
            "roi_0_y1",
            self.andor_camera_control,
        )


class MeasureDoubleDipoleTrapFrag(
    DoubleTrapImagingBGSubtracted, _MeasureDipoleTrapBase
):
    pass


class NormalizedDoubleDipoleTrapFrag(
    DoubleTrapImagingNormalised, _MeasureDipoleTrapBase
):
    pass


MeasureDipoleTrap = make_fragment_scan_exp(MeasureDipoleTrapFrag)
MeasureDoubleDipoleTrap = make_fragment_scan_exp(MeasureDoubleDipoleTrapFrag)
NormalizedDoubleDipoleTrap = make_fragment_scan_exp(NormalizedDoubleDipoleTrapFrag)
