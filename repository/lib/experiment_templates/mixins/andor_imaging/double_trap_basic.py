import logging

from repository.lib import constants

from .single_andor_image import SingleAndorImage

logger = logging.getLogger(__name__)
DATASET_NAME = "single_andor_image"


class DoubleTrapImagingBasic(SingleAndorImage):
    """
    Image two traps with a single fluorescence pulse

    This is a mixin - see the documentation for :mod:`~.red_mot_experiment` for
    details.

    Kernel hooks used (multiple mixins cannot use the same hooks):

    * :meth:`~do_imaging_hook_andor`
    """

    num_andor_images = 1
    num_grabber_readouts = 1
    num_grabber_rois = 2

    def build_fragment(self):
        super().build_fragment()

        # Set default ROIs
        self.setattr_param_rebind(
            "roi_0_x0",
            self.andor_camera_control,
            default=constants.ANDOR_ROI_DIPOLE_TRAP_FORWARD_X0,
        )
        self.setattr_param_rebind(
            "roi_0_x1",
            self.andor_camera_control,
            default=constants.ANDOR_ROI_DIPOLE_TRAP_FORWARD_X1,
        )
        self.setattr_param_rebind(
            "roi_0_y0",
            self.andor_camera_control,
            default=constants.ANDOR_ROI_DIPOLE_TRAP_FORWARD_Y0,
        )
        self.setattr_param_rebind(
            "roi_0_y1",
            self.andor_camera_control,
            default=constants.ANDOR_ROI_DIPOLE_TRAP_FORWARD_Y1,
        )

        self.setattr_param_rebind(
            "roi_1_x0",
            self.andor_camera_control,
            default=constants.ANDOR_ROI_DIPOLE_TRAP_BACKWARD_X0,
        )
        self.setattr_param_rebind(
            "roi_1_x1",
            self.andor_camera_control,
            default=constants.ANDOR_ROI_DIPOLE_TRAP_BACKWARD_X1,
        )
        self.setattr_param_rebind(
            "roi_1_y0",
            self.andor_camera_control,
            default=constants.ANDOR_ROI_DIPOLE_TRAP_BACKWARD_Y0,
        )
        self.setattr_param_rebind(
            "roi_1_y1",
            self.andor_camera_control,
            default=constants.ANDOR_ROI_DIPOLE_TRAP_BACKWARD_Y1,
        )
