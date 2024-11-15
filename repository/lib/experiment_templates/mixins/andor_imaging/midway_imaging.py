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


class MidSequenceAndorImage(AndorImagingBase):
    """
    Image midway through the sequence, expressed as time since the start of the
    broadband red MOT

    This mixin will override the usual "do_imaging_hook_andor" to do nothing,
    and will instead pre-schedule imaging to occur midway through the sequence,
    without turning any of the other beams off. This might mean that you get
    lots of scatter! Particularly from the 1064, or if you image shortly after
    the shelving clearout pulse, before the camera has had time to recover. If
    you are using EM gain, be careful not to damage the sensor by setting a
    large clearout blue pulse and then imaging during it.

    This mixin will also take a background image at the end of the sequence.

    TODO: Consider running the whole sequence twice, one with no atoms, so that
    the background image can be in the same place as the real one. Slow
    obviously, but we don't care.

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
            "delay_before_imaging",
            FloatParam,
            description="Delay before imaging, relative to start of BB MOT",
            min=0,
            unit="ms",
            default=100e-3,
        )
        self.delay_before_bg_pulse: FloatPajramHandle

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
        self.setattr_result("andor_mean_bg_corrected", FloatChannel)
        self.andor_mean_bg_corrected: FloatChannel

    @kernel
    def do_imaging_hook_andor(self):
        """
        Hook for the imaging sequence. This hook runs after the spectroscopy
        etc. is completed, and should handle imaging with the Andor camera.
        """

        # FIXME: Ensure this is after the imaging pulse

        # Take the background image. The foreground image should have already happened
        delay(self.delay_before_bg_pulse.get())
        self.do_pulse()

    @host_only
    def update_andor_monitor_hook(self, images):
        """
        Update the andor monitor with an appropriate image

        By default, AndorImagingBase would show the first image. We show the
        bg-corrected data instead.
        """
        # FIXME
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
        self.andor_mean_bg_corrected.push(means[0] - means[1])
