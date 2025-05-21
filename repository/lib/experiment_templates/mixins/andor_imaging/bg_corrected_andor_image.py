import logging

import numpy as np
from artiq.experiment import delay
from artiq.experiment import host_only
from artiq.experiment import kernel
from ndscan.experiment import FloatChannel
from ndscan.experiment.parameters import FloatParam
from ndscan.experiment.parameters import FloatParamHandle

from repository.lib import constants
from repository.lib.experiment_templates.mixins.andor_imaging.imaging_base import (
    ANDOR_MONITOR_DATASET,
)
from repository.lib.experiment_templates.mixins.andor_imaging.imaging_base import (
    AndorImagingBase,
)

logger = logging.getLogger(__name__)


class BGCorrectedAndorImage(AndorImagingBase):
    """
    Image with a single fluorescence pulse using the Andor camera then take another for background subtraction

    This is a mixin - see the documentation for :mod:`~.red_mot_experiment` for
    details.

    Kernel hooks used (multiple mixins cannot use the same hooks):

    * :meth:`~do_imaging_hook_andor`
    * :meth:`~process_andor_data_hook`
    * :meth:`~update_andor_monitor_hook`
    """

    num_andor_images = 2
    num_images_per_series = 2
    num_grabber_readouts = 2
    num_grabber_rois = 1

    def build_fragment(self):
        super().build_fragment()

        self.setattr_param(
            "delay_before_bg_pulse",
            FloatParam,
            description="Delay before background pulse",
            min=0,
            unit="ms",
            default=constants.ANDOR_CAMERA_BACKGROUND_DELAY,
        )
        self.delay_before_bg_pulse: FloatParamHandle
        self.bg_imaging_make_result_channel()

    def bg_imaging_make_result_channel(self):
        # AndorImagingBase makes sum and mean ResultChannels automatically, but
        # we create another one for the bg-corrected data
        self.setattr_result(
            "andor_mean_bg_corrected", FloatChannel, display_hints={"priority": -1}
        )
        self.andor_mean_bg_corrected: FloatChannel

        self.setattr_result(
            "andor_sum_bg_corrected", FloatChannel, display_hints={"priority": -1}
        )
        self.andor_sum_bg_corrected: FloatChannel

    @kernel
    def do_imaging_hook_andor(self):
        """
        Hook for the imaging sequence. This hook runs after the spectroscopy
        etc. is completed, and should handle imaging with the Andor camera.
        """
        # Image atoms
        self.do_pulse()

        # Drop them
        self.blue_3d_mot.chamber_2_field_setter.set_mot_gradient(0.0)

        delay(self.delay_before_bg_pulse.get())

        # Image background with no atoms
        self.do_pulse()

    @host_only
    def update_andor_monitor_hook(self, images):
        """
        Update the andor monitor with an appropriate image

        By default, AndorImagingBase would show the first image. We show the
        bg-corrected data instead.
        """
        img_array = images[0]
        bg_img_array = images[1]
        corrected_img_array = np.int32(img_array) - np.int32(bg_img_array)

        self.set_dataset(
            ANDOR_MONITOR_DATASET,
            corrected_img_array,
            broadcast=True,
            persist=False,
            archive=False,
        )

    @kernel
    def process_grabber_data_hook(self, sums, means):
        self.andor_sum_bg_corrected.push(sums[0] - sums[1])
        self.andor_mean_bg_corrected.push(means[0] - means[1])

    # @host_only
    # def process_andor_image_hook(self, imgs_array):
    #     super().process_andor_image_hook(imgs_array)

    @host_only
    def do_gauss_fit_hook(self, img_array):
        img_array = img_array[0]
        bg_img_array = img_array[1]
        corrected_img_array = np.int32(img_array) - np.int32(bg_img_array)
        self.fit_from_grabber_rois(corrected_img_array)


class BGCorrectedAndorImageSingleXODT(BGCorrectedAndorImage):
    """
    Image with a single fluorescence pulse using the Andor camera then take another for background subtraction

    ROI set for the single, "forward" XODT
    """

    def get_grabber_roi_defaults(self, num_grabber_rois):
        return [
            [
                constants.ANDOR_ROI_DIPOLE_TRAP_FORWARD_X0,
                constants.ANDOR_ROI_DIPOLE_TRAP_FORWARD_Y0,
                constants.ANDOR_ROI_DIPOLE_TRAP_FORWARD_X1,
                constants.ANDOR_ROI_DIPOLE_TRAP_FORWARD_Y1,
            ]
            * num_grabber_rois
        ]
