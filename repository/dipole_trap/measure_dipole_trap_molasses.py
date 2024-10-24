import logging

from artiq.experiment import kernel
from ndscan.experiment.entry_point import make_fragment_scan_exp

from repository.lib import constants
from repository.lib.experiment_templates.mixins.bg_corrected_andor_image import (
    BGCorrectedAndorImage,
)
from repository.lib.experiment_templates.mixins.flir_measurement import (
    FLIRMeasurementMixin,
)
from repository.lib.experiment_templates.mixins.ndscan_analysis_exponential_decay import (
    ExponentialDecayMixin,
)
from repository.lib.experiment_templates.mixins.single_andor_image import (
    SingleAndorImage,
)
from repository.lib.experiment_templates.mixins.XODT_molasses import XODTMolassesMixin

logger = logging.getLogger(__name__)

EXPOSE_MOLASSES_1_PARAMS = True
EXPOSE_MOLASSES_2_PARAMS = True


class MeasureDipoleTrapFrag(
    BGCorrectedAndorImage,
    FLIRMeasurementMixin,
    ExponentialDecayMixin,
    SingleAndorImage,
    XODTMolassesMixin,
):
    """
    Load a dipole trap, do 689 nm molasses, hold, and take BG subtracted image
    """

    def build_fragment(self):
        super().build_fragment()

        # Remove unused parameters
        self.override_param("spectroscopy_field_gradient", 0)

        # Expose the bias field for moving the MOT to the right place
        self.setattr_param_rebind(
            "chamber_2_bias_x",
            self.blue_3d_mot,
            default=constants.BIAS_DURING_MOTS_FOR_MOLASSES[0],
        )
        self.setattr_param_rebind(
            "chamber_2_bias_y",
            self.blue_3d_mot,
            default=constants.BIAS_DURING_MOTS_FOR_MOLASSES[1],
        )
        self.setattr_param_rebind(
            "chamber_2_bias_z",
            self.blue_3d_mot,
            default=constants.BIAS_DURING_MOTS_FOR_MOLASSES[2],
        )
        self.setattr_param_rebind(
            "chamber_2_red_narrowband_mot_current_start",
            self.red_mot.narrow_red_compression_phase,
            original_name="chamber_2_mot_current_start",
            default=constants.RED_COMPRESSION_MOT_CURRENT_START_FOR_MOLASSES,
        )
        self.setattr_param_rebind(
            "chamber_2_red_narrowband_mot_current_end",
            self.red_mot.narrow_red_compression_phase,
            original_name="chamber_2_mot_current_end",
            default=constants.RED_COMPRESSION_MOT_CURRENT_END_FOR_MOLASSES,
        )

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

        # Expose the molasses ramp parameters if desired
        if EXPOSE_MOLASSES_1_PARAMS:
            names = [_ for _ in self.molasses_xodt_1._free_params.keys()]
            for name in names:
                self.setattr_param_rebind(
                    f"molasses_1_{name}", self.molasses_xodt_1, original_name=name
                )
        if EXPOSE_MOLASSES_2_PARAMS:
            names = [_ for _ in self.molasses_xodt_2._free_params.keys()]
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


MeasureDipoleTrap = make_fragment_scan_exp(MeasureDipoleTrapFrag)
