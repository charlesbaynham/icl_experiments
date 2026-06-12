import logging
from typing import Callable

import numpy as np
from artiq.language import at_mu
from artiq.language import delay
from artiq.language import delay_mu
from artiq.language import host_only
from artiq.language import kernel
from artiq.language import now_mu
from ndscan.experiment import FloatChannel
from ndscan.experiment.parameters import FloatParam
from ndscan.experiment.parameters import FloatParamHandle
from numpy import int64

from repository.lib import constants
from repository.lib.experiment_templates.mixins.andor_imaging.bg_corrected_andor_image import (
    BGCorrectedAndorImageConfig,
)
from repository.lib.experiment_templates.mixins.andor_imaging.imaging_base import (
    ANDOR_MONITOR_DATASET,
)
from repository.lib.experiment_templates.mixins.andor_imaging.imaging_base import (
    AndorImagingBase,
)
from repository.lib.fragments.blue_3d_mot import Blue3DMOTFrag
from repository.lib.fragments.cameras.andor_camera import AndorCameraConfig
from repository.lib.fragments.checkpoint_fragment import RedMOTCheckpoints

logger = logging.getLogger(__name__)


class _MidSequenceAndorImageFrag(RedMOTCheckpoints):
    """
    Self-cascading subfragment that implements the midway-imaging behaviour.

    The ``start_of_red_broadband_checkpoint`` schedules the foreground image
    midway through the sequence and then rewinds the timeline. The
    non-checkpoint ``do_imaging_hook_andor`` and ``update_andor_monitor_hook``
    are co-located here because they share the ``t_imaging_done_mu`` state set
    by the checkpoint; the parent mixin forwards to them.
    """

    def build_fragment(self, blue_3d_mot: Blue3DMOTFrag, do_pulse: Callable):
        self.kernel_invariants = getattr(self, "kernel_invariants", set())

        self.blue_3d_mot = blue_3d_mot
        self.kernel_invariants.add("blue_3d_mot")

        # The "do_pulse" method lives on the parent fragment. We keep a
        # reference to it so it can be called from this subfragment.
        self.do_pulse = do_pulse

        self.setattr_device("core")

        self.setattr_param(
            "delay_before_imaging",
            FloatParam,
            description="Delay before imaging, relative to start of BB MOT",
            min=0,
            unit="ms",
            default=100e-3,
        )
        self.delay_before_imaging: FloatParamHandle

        self.setattr_param(
            "delay_before_bg_pulse",
            FloatParam,
            description="Delay before background pulse",
            min=0,
            unit="ms",
            default=constants.ANDOR_CAMERA_BACKGROUND_DELAY,
        )
        self.delay_before_bg_pulse: FloatParamHandle

        self.setattr_param(
            "repumping_time",
            FloatParam,
            description="Time to repump atoms before imaging",
            min=0.0,
            unit="ms",
            default=0.0,
        )
        self.repumping_time: FloatParamHandle

        self.t_imaging_done_mu = int64(0)

    @kernel
    def start_of_red_broadband_checkpoint(self):
        """
        Schedule an image to be taken midway through the sequence, then reset
        the timeline to leave it unaltered. This will certainly consume a
        lane
        """
        self.start_of_red_broadband_checkpoint_subfragments()

        delay_mu(int64(self.core.ref_multiplier))

        t_start_mu = now_mu()

        delay(-self.repumping_time.get())
        self.blue_3d_mot.turn_on_repumpers()
        delay(self.repumping_time.get())
        self.blue_3d_mot.turn_off_repumpers()

        delay(self.delay_before_imaging.get())
        self.do_pulse()

        # Record the time at which imaging was completed so that we can ensure the background pulse is afterwards
        self.t_imaging_done_mu = now_mu()

        # Reset the timeline
        at_mu(t_start_mu)

    @kernel
    def do_imaging_hook_andor(self):
        """
        Take the background image

        If the imaging pulse happened at least delay_before_bg_pulse ago then
        take the bg pulse now, otherwise wait until that time.
        """

        delay(self.delay_before_bg_pulse.get())

        # Delay the bg image if necessary
        t_earliest_bg_pulse_start_mu = self.t_imaging_done_mu + self.core.seconds_to_mu(
            self.delay_before_bg_pulse.get()
        )
        if now_mu() < t_earliest_bg_pulse_start_mu:
            at_mu(t_earliest_bg_pulse_start_mu)

        # Take the background image. The foreground image should have already happened
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


class MidSequenceAndorImageMixin(AndorImagingBase):
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
    * :meth:`~start_of_red_broadband_checkpoint`
    * :meth:`~process_andor_data_hook`
    * :meth:`~update_andor_monitor_hook`
    """

    num_andor_images = 2
    num_images_per_series = 2
    num_grabber_readouts = 2
    num_grabber_rois = 1

    def get_andor_camera_config_hook(self) -> AndorCameraConfig:
        f = self.setattr_fragment(
            "andor_camera_config",
            BGCorrectedAndorImageConfig,
            default_roi=[
                constants.ANDOR_ROI_X0,
                constants.ANDOR_ROI_Y0,
                constants.ANDOR_ROI_X1,
                constants.ANDOR_ROI_Y1,
            ],
        )
        return f  # type: ignore

    def build_fragment(self):
        super().build_fragment()

        # Meaningless without an experiment:
        self.override_param("delay_after_experiment", 0)

        self.bg_imaging_make_result_channel()

        # Initiate the subfragment that implements the midway-imaging
        # checkpoint (and the coupled hooks that share its timing state).
        self.setattr_fragment(
            "mid_sequence_frag",
            _MidSequenceAndorImageFrag,
            blue_3d_mot=self.blue_3d_mot,
            do_pulse=self.do_pulse,
        )
        self.mid_sequence_frag: _MidSequenceAndorImageFrag

    def bg_imaging_make_result_channel(self):
        # AndorImagingBase makes sum and mean ResultChannels automatically, but
        # we create another one for the bg-corrected data
        self.setattr_result("andor_mean_bg_corrected", FloatChannel)
        self.andor_mean_bg_corrected: FloatChannel

    # From here on, forward the appropriate hooks to the subfragment that
    # implements the midway-imaging behaviour.

    @kernel
    def do_imaging_hook_andor(self):
        self.mid_sequence_frag.do_imaging_hook_andor()

    @host_only
    def update_andor_monitor_hook(self, images):
        self.mid_sequence_frag.update_andor_monitor_hook(images)

    @kernel
    def do_experiment_after_dipole_trap_hook(self):
        # No experiment needed, do nothing
        pass

    @kernel
    def process_grabber_data_hook(self, sums, means):
        self.andor_mean_bg_corrected.push(means[0] - means[1])
