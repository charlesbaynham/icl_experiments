import logging

import numpy as np
from artiq.language import kernel
from artiq.language import portable
from ndscan.experiment.parameters import IntParam
from ndscan.experiment.parameters import IntParamHandle

from repository.lib import constants
from repository.lib.experiment_templates.mixins.andor_imaging.imaging_base import (
    AndorImagingBase,
)
from repository.lib.fragments.cameras.andor_camera import AndorCameraConfig

logger = logging.getLogger(__name__)


class SingleAndorImageConfig(AndorCameraConfig):
    """
    Camera config for a single fluorescence pulse with one grabber ROI.
    """

    num_andor_images = 1
    num_images_per_series = 1
    num_grabber_readouts = 1
    num_grabber_rois = 1

    def build_fragment(
        self,
        default_roi: list[int] = None,  # type: ignore
    ):
        super().build_fragment()

        if default_roi is None:
            raise ValueError("Must provide default ROI for SingleAndorImageConfig")

        self.setattr_param(
            "roi_x0",
            IntParam,
            "Grabber ROI x0",
            default=default_roi[0],
            min=0,
            max=512,
        )
        self.setattr_param(
            "roi_y0",
            IntParam,
            "Grabber ROI y0",
            default=default_roi[1],
            min=0,
            max=1024,
        )
        self.setattr_param(
            "roi_x1",
            IntParam,
            "Grabber ROI x1",
            default=default_roi[2],
            min=0,
            max=512,
        )
        self.setattr_param(
            "roi_y1",
            IntParam,
            "Grabber ROI y1",
            default=default_roi[3],
            min=0,
            max=1024,
        )
        self.roi_x0: IntParamHandle
        self.roi_x1: IntParamHandle
        self.roi_y0: IntParamHandle
        self.roi_y1: IntParamHandle

        self.roi_buffer = [[np.int32(0)] * 4] * self.num_grabber_rois

    @portable
    def get_rois(self):
        self.roi_buffer[0][0] = self.roi_x0.get()
        self.roi_buffer[0][1] = self.roi_y0.get()
        self.roi_buffer[0][2] = self.roi_x1.get()
        self.roi_buffer[0][3] = self.roi_y1.get()
        return self.roi_buffer


class SingleAndorImage(AndorImagingBase):
    """
    Image with a single fluorescence pulse using the Andor camera

    This is a mixin - see the documentation for :mod:`~.red_mot_experiment` for
    details.

    Kernel hooks used (multiple mixins cannot use the same hooks):

    * :meth:`~do_imaging_hook_andor`
    * :meth:`~start_of_red_broadband_hook` (from AndorImagingBase)
    * :meth:`~save_grabber_data_hook` (from AndorImagingBase)


    """

    def get_andor_camera_config_hook(self) -> AndorCameraConfig:
        f = self.setattr_fragment(
            "andor_camera_config",
            SingleAndorImageConfig,
            default_roi=[
                constants.ANDOR_ROI_X0,
                constants.ANDOR_ROI_Y0,
                constants.ANDOR_ROI_X1,
                constants.ANDOR_ROI_Y1,
            ],
        )
        return f  # type: ignore

    @kernel
    def do_imaging_hook_andor(self):
        # Just image the atoms once
        self.do_pulse()

    @kernel
    def process_grabber_data_hook(self, sums, means):
        # No special processing - the base class already pushes sums/means to
        # result channels.
        pass
