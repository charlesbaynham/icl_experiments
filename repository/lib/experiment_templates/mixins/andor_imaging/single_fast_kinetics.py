import logging

import numpy as np
from artiq.language import at_mu
from artiq.language import delay
from artiq.language import delay_mu
from artiq.language import kernel
from artiq.language import now_mu
from artiq.language import rpc
from ndscan.experiment import FloatChannel
from ndscan.experiment.parameters import FloatParam
from ndscan.experiment.parameters import FloatParamHandle
from ndscan.experiment.parameters import IntParam
from ndscan.experiment.parameters import IntParamHandle

from repository.lib import constants
from repository.lib.experiment_templates.mixins.andor_imaging.imaging_base import (
    AndorImagingBase,
)
from repository.lib.fragments.cameras.andor_camera import AndorCameraControl

logger = logging.getLogger(__name__)
ANDOR_FK_G_BG_CORR_DATASET = "g_bg_corrected"
ANDOR_FK_E_BG_CORR_DATASET = "e_bg_corrected"


def calculate_grabber_rois(
    fast_kinetics_height,
    fast_kinetics_offset,
    num_images,
    x0,
    y0,
    x1,
    y1,
    bg_width,
    excited_shift,
):
    """
    Given an ROI (x0, y0, x1, y1) on the full image, calculate the required ROI
    when in fast kinetics mode. This specific method also calculates the background ROIs
    which are on the sides of the signal ROIs.
    Note: We only need the coords of the signal ROI. The background ROIs are calculated based on the signal ROI coords and the specified width. The excited state ROIS
    cen be shifted downwards to compensate the fall under gravity with excited_shift.
    """

    logger.debug(
        "fast_kinetics_height, fast_kinetics_offset, num_images, x0, y0, x1, y1",
        (fast_kinetics_height, fast_kinetics_offset, num_images, x0, y0, x1, y1),
    )

    if y1 > fast_kinetics_height + fast_kinetics_offset:
        raise ValueError(
            "The fast kinetics region is not large enough to cover the full ROI"
        )

    signal_rois = [
        [
            x0,
            y0 + i * (fast_kinetics_height - excited_shift) - fast_kinetics_offset,
            x1,
            y1 + i * (fast_kinetics_height - excited_shift) - fast_kinetics_offset,
        ]
        for i in range(num_images)
    ]

    background_rois = [
        [
            x0 - bg_width,
            y0 + i * (fast_kinetics_height - excited_shift) - fast_kinetics_offset,
            x0,
            y1
            + i * (fast_kinetics_height - excited_shift)
            - fast_kinetics_offset
            + 25,  # FIXME Debugging code? Uncommitted
        ]
        for i in range(num_images)
    ] + [
        [
            x1,
            y0 + i * (fast_kinetics_height - excited_shift) - fast_kinetics_offset,
            x1 + bg_width,
            y1
            + i * (fast_kinetics_height - excited_shift)
            - fast_kinetics_offset
            + 25,  # FIXME Debugging code? Uncommitted
        ]
        for i in range(num_images)
    ]

    return signal_rois + background_rois


class SingleImageNormalisedFastKineticsBase(AndorImagingBase):
    """
    This is the base class for single image normalised fast kinetics.

    I don't know what I'm doing :')
    """

    num_andor_images = 2
    num_grabber_readouts = 1
    num_grabber_rois = 6
    num_images_per_series = 2
    fast_kinetics_height_default = constants.ANDOR_FAST_KINETICS_HEIGHT
    fast_kinetics_offset_default = constants.ANDOR_FAST_KINETICS_OFFSET

    def build_fragment(self):
        super().build_fragment()

        self.setattr_param(
            "delay_between_imaging_pulses",
            FloatParam,
            "Time between the start of each fluorescence pulse",
            default=3.5e-3,
            unit="ms",
        )

        self.setattr_param(
            "background_horizontal_width",
            IntParam,
            "The width of the ROIs in the horizontal direction, in pixels. This is used for both the left and right background ROIs.",
            default=constants.ANDOR_SINGLE_FAST_KINETICS_BACKGROUND_ROI_WIDTH,
        )

        self.delay_between_imaging_pulses: FloatParamHandle
        # Note the wording of this parameter - it's the time between the starts
        # of the pulses, not the time the end of one and the start of the next
        # one. This interacts non-trivially with the way that the Andor camera
        # clocks out rows of the EMCCD in Fast Kinetics Mode. See the comments
        # in :mod:`~.andor_camera` and the lab book entry from 2024-10-30 for
        # more detail.

        self.background_horizontal_width: IntParamHandle

        # Force the camera's fast kinetics shot time to match our pulse time
        self.andor_camera_control.bind_param(
            "fast_kinetics_time_between_shots",
            self.delay_between_imaging_pulses,
        )

        self.fast_kinetics_setup_results()

    def host_setup(self):
        super().host_setup()
        default_rois = self.get_monitor_rois()
        self.ccb.issue(
            "create_applet",
            "Ground bg corrected",
            f"${{python}} -m custom_artiq_applets.full_img_applet {ANDOR_FK_G_BG_CORR_DATASET} --dataset_prefix 'g_bg_corrected' --default_rois '{default_rois}'",
        )
        self.ccb.issue(
            "create_applet",
            "Excited bg corrected",
            f"${{python}} -m custom_artiq_applets.full_img_applet {ANDOR_FK_E_BG_CORR_DATASET} --dataset_prefix 'e_bg_corrected' --default_rois '{default_rois}'",
        )

    def fast_kinetics_setup_results(self):
        self.setattr_result("excitation_fraction", FloatChannel)
        self.setattr_result("atom_number", FloatChannel)

        self.excitation_fraction: FloatChannel
        self.atom_number: FloatChannel

    def hook_setup_andor(self):
        """
        Setup the Andor camera to use 3x ROIs since we're expecting fast
        kinetics mode with 3 images
        """

        self.setattr_fragment(
            "andor_camera_control",
            AndorCameraControl,
            roi_defaults=self.get_grabber_roi_defaults(),
            fast_kinetics_height_default=self.fast_kinetics_height_default,
            fast_kinetics_offset_default=self.fast_kinetics_offset_default,
            add_pre_trigger_delay=True,
            fast_kinetics_num_shots=self.num_images_per_series,
        )
        self.andor_camera_control: AndorCameraControl

        self.hook_setup_andor_results()

    def get_grabber_roi_defaults(self):
        return calculate_grabber_rois(
            fast_kinetics_height=self.fast_kinetics_height_default,
            fast_kinetics_offset=self.fast_kinetics_offset_default,
            num_images=self.num_images_per_series,
            x0=constants.ANDOR_ROI_X0,
            y0=constants.ANDOR_ROI_Y0,
            x1=constants.ANDOR_ROI_X1,
            y1=constants.ANDOR_ROI_Y1,
            bg_width=self.background_horizontal_width.get(),
            excited_shift=constants.ROI_SHIFT_EXCITED_STATE,
        )

    @kernel
    def do_imaging_hook_andor(self):
        """
        Hook for the imaging sequence. This hook runs after the spectroscopy
        etc. is completed, and should handle imaging with the Andor camera.
        """
        self.do_image()
        # t_post_mu = now_mu()
        # delay(0.5)
        # self.post_first_series()  # call rpc to get images
        # at_mu(t_post_mu)
        # delay(self.delay_before_bg_img.get())

    @kernel
    def do_image(self):
        # Image ground state atoms
        t_start_mu = now_mu()
        self.do_first_pulse()

        # Image excited state atoms
        at_mu(t_start_mu)
        delay(self.delay_between_imaging_pulses.get())
        self.do_second_pulse()

    @kernel
    def do_first_pulse(self):
        # Normal fluorescence pulse at now_mu() + camera trigger, pre-empted by
        # the time required to shift one Fast Kinetics region + a
        # pre_trigger_delay
        self.do_pulse()

    @kernel
    def do_second_pulse(self):
        # Just a fluorescence pulse - the camera has already been triggered and handles its own timings
        self.fluorescence_pulse.do_imaging_pulse(ignore_final_shutters=True)

    @kernel
    def post_first_series(self):
        """
        eg turn off beams, start acquisition
        """
        self.post_first_series_rpc()

    @rpc
    def post_first_series_rpc(self):
        self.image_store = []  # clear the image store
        self.image_store += self.get_andor_images()
        self.andor_camera_control.start_acquisition()

    @kernel
    def get_roi_area(self, roi):
        return (roi[2] - roi[0]) * (roi[3] - roi[1])

    @kernel
    def process_grabber_data_hook(self, sums, means):
        # The normalisation factor is the ratio of the number of pixels in the
        # background to signal ROIs. Since we have coerced the background ROIs
        # to have the same height as the signal ROIs, this is just 2x the ratio
        # of the widths (since we have two background ROIs, one on either side
        # of the signal ROI). Absolutely fucking awful code... but it works :)
        areas = [
            self.get_roi_area(
                [
                    self.andor_camera_control.roi_0_x0.get(),
                    self.andor_camera_control.roi_0_y0.get(),
                    self.andor_camera_control.roi_0_x1.get(),
                    self.andor_camera_control.roi_0_y1.get(),
                ]
            ),
            self.get_roi_area(
                [
                    self.andor_camera_control.roi_1_x0.get(),
                    self.andor_camera_control.roi_1_y0.get(),
                    self.andor_camera_control.roi_1_x1.get(),
                    self.andor_camera_control.roi_1_y1.get(),
                ]
            ),
            self.get_roi_area(
                [
                    self.andor_camera_control.roi_2_x0.get(),
                    self.andor_camera_control.roi_2_y0.get(),
                    self.andor_camera_control.roi_2_x1.get(),
                    self.andor_camera_control.roi_2_y1.get(),
                ]
            ),
            self.get_roi_area(
                [
                    self.andor_camera_control.roi_3_x0.get(),
                    self.andor_camera_control.roi_3_y0.get(),
                    self.andor_camera_control.roi_3_x1.get(),
                    self.andor_camera_control.roi_3_y1.get(),
                ]
            ),
            self.get_roi_area(
                [
                    self.andor_camera_control.roi_4_x0.get(),
                    self.andor_camera_control.roi_4_y0.get(),
                    self.andor_camera_control.roi_4_x1.get(),
                    self.andor_camera_control.roi_4_y1.get(),
                ]
            ),
            self.get_roi_area(
                [
                    self.andor_camera_control.roi_5_x0.get(),
                    self.andor_camera_control.roi_5_y0.get(),
                    self.andor_camera_control.roi_5_x1.get(),
                    self.andor_camera_control.roi_5_y1.get(),
                ]
            ),
        ]

        norm_factor_1 = areas[0] / (areas[2] + areas[4])
        norm_factor_2 = areas[1] / (areas[3] + areas[5])

        atom_num_1 = sums[0] - norm_factor_1 * (sums[2] + sums[4])
        atom_num_2 = sums[1] - norm_factor_2 * (sums[3] + sums[5])
        atom_number = atom_num_1 + atom_num_2

        if atom_number == 0:
            self.excitation_fraction.push(0.0)
        else:
            self.excitation_fraction.push(atom_num_2 / atom_number)

        self.atom_number.push(atom_number)

    @rpc(flags={"async"})
    def process_andor_image_hook(self, images: np.array):
        super().process_andor_image_hook(images)
        # Ok this is copied from normalised_fast_kinetics_base but idk what it does
        ground_bg_corrected = images[0].astype(int)
        excited_bg_corrected = images[1].astype(int)
        self.set_dataset(
            ANDOR_FK_G_BG_CORR_DATASET,
            ground_bg_corrected,
            broadcast=True,
            persist=False,
            archive=False,
        )
        self.set_dataset(
            ANDOR_FK_E_BG_CORR_DATASET,
            excited_bg_corrected,
            broadcast=True,
            persist=False,
            archive=False,
        )


class SingleImageNormalisedDipoleTrapFastKineticsMixin(
    SingleImageNormalisedFastKineticsBase
):
    """
    Implements normalised readout for a :py:class:`~RedMOTWithExperiment`
    experiment

    This is a mixin - see the documentation for :mod:`~.red_mot_experiment` for
    details.

    Kernel hooks used (multiple mixins cannot use the same hooks):

    * :meth:`~do_imaging_hook_andor`
    * :meth:`~process_andor_data_hook`
    * :meth:`~update_andor_monitor_hook`
    """

    fast_kinetics_height_default = constants.ANDOR_FAST_KINETICS_HEIGHT_DIPOLE_TRAP
    fast_kinetics_offset_default = constants.ANDOR_FAST_KINETICS_OFFSET_DIPOLE_TRAP

    def get_grabber_roi_defaults(self):
        return calculate_grabber_rois(
            fast_kinetics_height=self.fast_kinetics_height_default,
            fast_kinetics_offset=self.fast_kinetics_offset_default,
            num_images=self.num_images_per_series,
            x0=constants.ANDOR_ROI_DIPOLE_TRAP_FORWARD_SINGLE_IMAGE_X0,
            y0=constants.ANDOR_ROI_DIPOLE_TRAP_FORWARD_SINGLE_IMAGE_Y0,
            x1=constants.ANDOR_ROI_DIPOLE_TRAP_FORWARD_SINGLE_IMAGE_X1,
            y1=constants.ANDOR_ROI_DIPOLE_TRAP_FORWARD_SINGLE_IMAGE_Y1,
            bg_width=constants.ANDOR_SINGLE_FAST_KINETICS_BACKGROUND_ROI_WIDTH,
            excited_shift=constants.ROI_SHIFT_EXCITED_STATE,
        )


class SingleImageNormalisedFastKineticsRepumpedMixin(
    SingleImageNormalisedFastKineticsBase
):
    """
    Adds repumping after the first fluorescence pulse to a
    :class:`~.NormalisedFastKineticsBase` experiment.

    This is a mixin for :class:`~.NormalisedFastKineticsBase`.

    Kernel hooks used (multiple mixins cannot use the same hooks):

    * :meth:`~do_first_pulse`
    * :meth:`~do_imaging_hook_andor`
    """

    def build_fragment(self):
        super().build_fragment()

        self.setattr_param(
            "delay_repumps_after_first_pulse",
            FloatParam,
            "Delay after first fluorescence pulse before repumps turn on",
            default=0.01e-3,
            unit="ms",
        )
        self.delay_repumps_after_first_pulse: FloatParamHandle

    @kernel
    def do_first_pulse(self):
        self.do_pulse()
        delay(self.delay_repumps_after_first_pulse.get())
        self.blue_3d_mot.turn_on_repumpers()
