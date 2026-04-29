import abc
import logging

import numpy as np
from artiq.language import at_mu
from artiq.language import delay
from artiq.language import kernel
from artiq.language import now_mu
from artiq.language import rpc
from artiq.master.scheduler import Scheduler
from artiq_influx_generic import InfluxController
from ndscan.experiment import FloatChannel
from ndscan.experiment.parameters import FloatParam
from ndscan.experiment.parameters import FloatParamHandle
from ndscan.experiment.parameters import IntParam
from ndscan.experiment.parameters import IntParamHandle
from numpy.typing import NDArray

from repository.lib import constants
from repository.lib.experiment_templates.mixins.andor_imaging.imaging_base import (
    AndorImagingBase,
)
from repository.lib.experiment_templates.mixins.clock_spectroscopy import (
    ClockSpectroscopyBase,
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
            y1 + i * (fast_kinetics_height - excited_shift) - fast_kinetics_offset,
        ]
        for i in range(num_images)
    ] + [
        [
            x1,
            y0 + i * (fast_kinetics_height - excited_shift) - fast_kinetics_offset,
            x1 + bg_width,
            y1 + i * (fast_kinetics_height - excited_shift) - fast_kinetics_offset,
        ]
        for i in range(num_images)
    ]

    return signal_rois + background_rois


class SingleImageNormalisedFastKineticsBase(AndorImagingBase):

    # These must be filled out
    num_andor_images: int
    num_grabber_readouts: int
    num_grabber_rois: int
    num_images_per_series: int

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

        self.setattr_device("influx_logger")
        self.influx_logger: InfluxController

        self.setattr_device("scheduler")
        self.scheduler: Scheduler

        self.delay_between_imaging_pulses: FloatParamHandle
        # Note the wording of this parameter - it's the time between the starts
        # of the pulses, not the time the end of one and the start of the next
        # one. This interacts non-trivially with the way that the Andor camera
        # clocks out rows of the EMCCD in Fast Kinetics Mode. See the comments
        # in :mod:`~.andor_camera` and the lab book entry from 2024-10-30 for
        # more detail.

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

    def hook_setup_andor(self):
        """
        Setup the andor camera control with the grabber ROI defaults being yet to be defined!
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

    @abc.abstractmethod
    def get_grabber_roi_defaults(self):
        """
        This must be filled out in the base class
        """

    def calculate_gravitational_drop(self):
        """
        This function calculates the gravitational drop of the excited state relative to the ground state.
        It cannot be run before time_dropped_before_first_pulse() is defined.
        """

        velocity_at_first_pulse = (
            constants.scipy_constants.g * self.time_dropped_before_first_pulse()
        )
        distance_fallen_between_pulses = (
            velocity_at_first_pulse * constants.FAST_KINETICS_DELAY_BETWEEN_PULSES
            + 0.5
            * constants.scipy_constants.g
            * constants.FAST_KINETICS_DELAY_BETWEEN_PULSES**2
        )
        pixels_dropped_between_pulses = round(
            distance_fallen_between_pulses / constants.ANDOR_CAMERA_FACTS["pixel_size"]
        )

        logger.debug(
            "Compensating gravity drop with an offset of %s pixels",
            pixels_dropped_between_pulses,
        )

        return pixels_dropped_between_pulses

    @abc.abstractmethod
    def time_dropped_before_first_pulse(self):
        """
        Must be filled in!
        Should return a float which is the time dropped before the first pulse.
        This is used to calculate the gravitational shift of the excited state compared
        to the ground state.
        """

    @kernel
    def do_imaging_hook_andor(self):
        """
        Hook for the imaging sequence. This hook runs after the spectroscopy
        etc. is completed, and should handle imaging with the Andor camera.
        """
        self.do_image()

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
        """
        Cute little function to get the area of a pixel grid given the four corners in the order
        [x0, x1, y0, y1]
        """
        return (roi[2] - roi[0]) * (roi[3] - roi[1])

    @rpc(flags={"async"})
    def process_andor_image_hook(self, images: np.array):
        super().process_andor_image_hook(images)
        # Ok this is copied from normalised_fast_kinetics_base but idk what it does
        # TODO Look into this
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


class SingleImageNormalisedFastKineticsSingleTrapBase(
    SingleImageNormalisedFastKineticsBase
):
    """
    Implements normalised readout using a single image for a :py:class:`~RedMOTWithExperiment`
    experiment.

    This mixin base uses the Andor camera to take one fast kinetics series with two images and creates a
    ResultChannels for normalised state readout. The two images in the fast kinetics series images atoms that starts in (i)
    the ground state, and (ii) the excited state.
    The normalised image is then calculated by subtracting the counts of the signal ROI with an average background count that is calculated as followed:
    Consider two background ROIs with the same height as the signal ROI and a width of 50 pixels; the two images are placed immediately to the left and right of the signal ROI.
    The total sum of background ROI counts is divided by the number of pixels in the background ROI and multiplied by the number of pixels in the signal ROI to get the average background across the entire signal ROI.
    Finally this background count is subtracted from the total signal ROI to get a normalised value.

    Variant mixins based on this class are expected to reimplement get_grabber_roi_defaults
    and/or fast_kinetics_default_height and fast_kinetics_default_offset as needed.

    This is a mixin - see the documentation for :mod:`~.red_mot_experiment` for
    details.

    NOTE I HAVE OMITTED THE CODE FOR THE GAUSSIAN FIT BECAUSE I AM LAZY - Dillen

    Kernel hooks used (multiple mixins cannot use the same hooks):

    * :meth:`~do_imaging_hook_andor`
    * :meth:`~process_andor_data_hook`
    * :meth:`~update_andor_monitor_hook`
    """

    num_andor_images = 2
    num_grabber_readouts = 1
    num_grabber_rois = 6
    num_images_per_series = 2

    def fast_kinetics_setup_results(self):
        self.setattr_result("excitation_fraction", FloatChannel)
        self.setattr_result("atom_number", FloatChannel)
        self.setattr_result("ground_atom_number", FloatChannel)
        self.setattr_result("excited_atom_number", FloatChannel)

        self.excitation_fraction: FloatChannel
        self.atom_number: FloatChannel
        self.ground_atom_number: FloatChannel
        self.excited_atom_number: FloatChannel

    def get_grabber_roi_defaults(self):
        return calculate_grabber_rois(
            fast_kinetics_height=self.fast_kinetics_height_default,
            fast_kinetics_offset=self.fast_kinetics_offset_default,
            num_images=self.num_images_per_series,
            x0=constants.ANDOR_ROI_X0,
            y0=constants.ANDOR_ROI_Y0,
            x1=constants.ANDOR_ROI_X1,
            y1=constants.ANDOR_ROI_Y1,
            bg_width=self.calculate_gravitational_drop(),
            excited_shift=constants.ROI_SHIFT_EXCITED_STATE,
        )

    @kernel
    def process_grabber_data_hook(self, sums, means):
        # The normalisation factor is the ratio of the number of pixels in the background to signal ROIs. Since we have coerced the background ROIs to have the same height as the signal ROIs, this is just 2x the ratio of the widths (since we have two background ROIs, one on either side of the signal ROI).
        # Absolutely fucking awful code... but it works :)
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

        # ROI 0     : Ground state signal ROI
        # ROI 1     : Excited state signal ROI
        # ROI 2 & 6 : Ground state background ROI
        # ROI 3 & 5 : Excited state background ROI

        # TODO : This BG subtraction method is common to both of the double and single trap so in principle should be
        # in the top base class, but I need to figure out how the ROIs are defined.

        norm_factor_1 = areas[0] / (areas[2] + areas[4])
        norm_factor_2 = areas[1] / (areas[3] + areas[5])

        atom_num_1 = sums[0] - norm_factor_1 * (sums[2] + sums[4])
        atom_num_2 = sums[1] - norm_factor_2 * (sums[3] + sums[5])
        atom_number = atom_num_1 + atom_num_2

        if atom_number == 0:
            self.excitation_fraction.push(0.0)
        else:
            self.excitation_fraction.push(atom_num_2 / atom_number)

        # Save the atom number counts
        self.atom_number.push(atom_number)
        self.ground_atom_number.push(atom_num_1)
        self.excited_atom_number.push(atom_num_2)

        # NOTE : WE can log this information into the InfluxDB like in the double trap


class SingleImageNormalisedFastKineticsDoubleTrapBase(
    SingleImageNormalisedFastKineticsBase
):
    """
    Implements normalised readout for a :py:class:`~RedMOTWithExperiment`
    experiment

    This mixin base uses the Andor camera to two fast kinetics series with two images each and create
    ResultChannels for normalised state readout. The first series contains atoms that starts in (i)
    the ground state, and (ii) the excited state. The second series reproduces the conditions of the first,
    with a long delay to clear out atoms.

    Variant mixins based on this class are expected to reimplement get_grabber_roi_defaults
    and/or fast_kinetics_default_height and fast_kinetics_default_offset as needed.

    This is a mixin - see the documentation for :mod:`~.red_mot_experiment` for
    details.

    Kernel hooks used (multiple mixins cannot use the same hooks):

    * :meth:`~do_imaging_hook_andor`
    * :meth:`~process_andor_data_hook`
    * :meth:`~update_andor_monitor_hook`
    """

    num_andor_images = 2
    num_grabber_readouts = 1
    num_grabber_rois = 12
    num_images_per_series = 2

    def fast_kinetics_setup_results(self):
        self.setattr_result("excitation_fraction_forward", FloatChannel)
        self.setattr_result("atom_number_forward", FloatChannel)

        self.setattr_result("excitation_fraction_backward", FloatChannel)
        self.setattr_result("atom_number_backward", FloatChannel)

        self.setattr_result("atom_number_imbalance", FloatChannel)
        self.setattr_result("atom_number_total", FloatChannel)

        # Maybe we want information about the individual corrected ground and excited state atom number like in the single imaging code, but for now we will use the same result channels as in the old bg subtraction method.

        self.excitation_fraction_forward: FloatChannel
        self.atom_number_forward: FloatChannel
        self.excitation_fraction_backward: FloatChannel
        self.atom_number_backward: FloatChannel
        self.atom_number_imbalance: FloatChannel
        self.atom_number_total: FloatChannel

    def get_grabber_roi_defaults(self):
        # Calculate two ROIs assuming that the clouds do not drop.
        # NOTE: This is the default behaviour that will be overidden in most situations
        # We expect 12 ROIs in total 4 signal and 8 background

        # The excited state shift needs to be calculated by different mixins
        forward_rois = calculate_grabber_rois(
            fast_kinetics_height=self.fast_kinetics_height_default,
            fast_kinetics_offset=self.fast_kinetics_offset_default,
            num_images=self.num_images_per_series,
            x0=constants.ANDOR_ROI_DIPOLE_TRAP_FORWARD_X0,
            y0=constants.ANDOR_ROI_DIPOLE_TRAP_FORWARD_Y0,
            x1=constants.ANDOR_ROI_DIPOLE_TRAP_FORWARD_X1,
            y1=constants.ANDOR_ROI_DIPOLE_TRAP_FORWARD_Y1,
            bg_width=constants.ANDOR_SINGLE_FAST_KINETICS_BACKGROUND_ROI_WIDTH,
            excited_shift=self.calculate_gravitational_drop(),
        )

        backward_rois = calculate_grabber_rois(
            fast_kinetics_height=self.fast_kinetics_height_default,
            fast_kinetics_offset=self.fast_kinetics_offset_default,
            num_images=self.num_images_per_series,
            x0=constants.ANDOR_ROI_DIPOLE_TRAP_BACKWARD_X0,
            y0=constants.ANDOR_ROI_DIPOLE_TRAP_BACKWARD_Y0,
            x1=constants.ANDOR_ROI_DIPOLE_TRAP_BACKWARD_X1,
            y1=constants.ANDOR_ROI_DIPOLE_TRAP_BACKWARD_Y1,
            bg_width=constants.ANDOR_SINGLE_FAST_KINETICS_BACKGROUND_ROI_WIDTH,
            excited_shift=self.calculate_gravitational_drop(),
        )

        top_trap_rois = backward_rois
        bottom_trap_rois = forward_rois

        return top_trap_rois + bottom_trap_rois

    @kernel
    def process_grabber_data_hook(self, sums, means):
        # The normalisation factor is the ratio of the number of pixels in the background to signal ROIs. Since we have coerced the background ROIs to have the same height as the signal ROIs, this is just 2x the ratio of the widths (since we have two background ROIs, one on either side of the signal ROI).
        # Absolutely fucking awful code... but it works :)
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
            self.get_roi_area(
                [
                    self.andor_camera_control.roi_6_x0.get(),
                    self.andor_camera_control.roi_6_y0.get(),
                    self.andor_camera_control.roi_6_x1.get(),
                    self.andor_camera_control.roi_6_y1.get(),
                ]
            ),
            self.get_roi_area(
                [
                    self.andor_camera_control.roi_7_x0.get(),
                    self.andor_camera_control.roi_7_y0.get(),
                    self.andor_camera_control.roi_7_x1.get(),
                    self.andor_camera_control.roi_7_y1.get(),
                ]
            ),
            self.get_roi_area(
                [
                    self.andor_camera_control.roi_8_x0.get(),
                    self.andor_camera_control.roi_8_y0.get(),
                    self.andor_camera_control.roi_8_x1.get(),
                    self.andor_camera_control.roi_8_y1.get(),
                ]
            ),
            self.get_roi_area(
                [
                    self.andor_camera_control.roi_9_x0.get(),
                    self.andor_camera_control.roi_9_y0.get(),
                    self.andor_camera_control.roi_9_x1.get(),
                    self.andor_camera_control.roi_9_y1.get(),
                ]
            ),
            self.get_roi_area(
                [
                    self.andor_camera_control.roi_10_x0.get(),
                    self.andor_camera_control.roi_10_y0.get(),
                    self.andor_camera_control.roi_10_x1.get(),
                    self.andor_camera_control.roi_10_y1.get(),
                ]
            ),
            self.get_roi_area(
                [
                    self.andor_camera_control.roi_11_x0.get(),
                    self.andor_camera_control.roi_11_y0.get(),
                    self.andor_camera_control.roi_11_x1.get(),
                    self.andor_camera_control.roi_11_y1.get(),
                ]
            ),
        ]

        # TODO Check that the indices are correct

        norm_factor_ground_top = areas[0] / (areas[2] + areas[4])
        norm_factor_excited_top = areas[1] / (areas[3] + areas[5])
        norm_factor_ground_bottom = areas[6] / (areas[8] + areas[10])
        norm_factor_excited_bottom = areas[7] / (areas[9] + areas[11])

        atom_number_ground_top = areas[0] - norm_factor_ground_top * (
            areas[2] + areas[4]
        )
        atom_number_excited_top = areas[1] - norm_factor_excited_top * (
            areas[3] + areas[5]
        )
        atom_number_ground_bottom = areas[6] - norm_factor_ground_bottom * (
            areas[8] + areas[10]
        )
        atom_number_excited_bottom = areas[7] - norm_factor_excited_bottom * (
            areas[9] + areas[11]
        )

        atom_number_total = (
            atom_number_ground_top
            + atom_number_excited_top
            + atom_number_ground_bottom
            + atom_number_excited_bottom
        )
        atom_number_top = atom_number_excited_top + atom_number_ground_top
        atom_number_bottom = atom_number_excited_bottom + atom_number_ground_bottom

        if atom_number_top == 0:
            excitation_fraction_top = 0.0
        else:
            excitation_fraction_top = atom_number_excited_top / atom_number_top

        if atom_number_bottom == 0:
            excitation_fraction_bottom = 0.0
        else:
            excitation_fraction_bottom = atom_number_excited_bottom / atom_number_top

        if atom_number_total == 0:
            imbalance = 0.0
        else:
            imbalance = (atom_number_bottom + atom_number_top) / atom_number_total

        # Save and push
        self._double_trap_imaging_log_data(
            excitation_fraction_forward=excitation_fraction_bottom,
            excitation_fraction_backward=excitation_fraction_top,
            atom_number_fwd=atom_number_bottom,
            atom_number_bwd=atom_number_top,
            imbalance=imbalance,
            total=atom_number_total,
        )

    @rpc(flags={"async"})
    def _double_trap_imaging_log_data(
        self,
        excitation_fraction_forward: float,
        excitation_fraction_backward: float,
        atom_number_fwd: float,
        atom_number_bwd: float,
        imbalance: float,
        total: float,
    ) -> None:
        # Log to NDScan
        self.excitation_fraction_forward.push(excitation_fraction_forward)
        self.excitation_fraction_backward.push(excitation_fraction_backward)
        self.atom_number_forward.push(atom_number_fwd)
        self.atom_number_backward.push(atom_number_bwd)
        self.atom_number_imbalance.push(imbalance)
        self.atom_number_total.push(total)

        # Log to InfluxDB
        self.influx_logger.write(
            tags={
                "type": "xxodt_atom_stats",
                "rid": self.scheduler.rid,
            },
            fields={
                "excitation_fraction_forward": excitation_fraction_forward,
                "excitation_fraction_backward": excitation_fraction_backward,
                "atom_number_forward": atom_number_fwd,
                "atom_number_backward": atom_number_bwd,
                "atom_number_imbalance": imbalance,
                "atom_number_total": total,
            },
        )


class SingleImageNormalisedFastKineticsDoubleTrapRepumpedBase(
    SingleImageNormalisedFastKineticsDoubleTrapBase
):
    """
    Adds repumping after the first fluorescence pulse to a
    :class:`~.SingleImageNormalisedFastKineticsDoubleTrapBase` experiment.

    This is a mixin for :class:`~.SingleImageNormalisedFastKineticsDoubleTrapBase`.

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

    def time_dropped_before_first_pulse(self):
        return ()


class SingleImageNormalisedFastKineticsDoubleTrapClockPulseBase(
    SingleImageNormalisedFastKineticsDoubleTrapBase, ClockSpectroscopyBase
):
    """
    Adds a clock pi pulse after the first fluorescence pulse to a
    :class:`~.SingleImageNormalisedFastKineticsDoubleTrapBase` experiment, in order to selectively
    bring the excited state in the ground state before imaging.

    This is a mixin for :class:`~.SingleImageNormalisedFastKineticsDoubleTrapBase`.

    Kernel hooks used (multiple mixins cannot use the same hooks):

    * :meth:`~do_first_pulse`
    * :meth:`~do_imaging_hook_andor`
    """

    def build_fragment(self):
        super().build_fragment()

        self.setattr_param(
            "delay_clock_after_first_pulse",
            FloatParam,
            "Delay after first fluorescence pulse before the pi pulse",
            default=0.01e-3,
            unit="ms",
        )
        self.delay_clock_after_first_pulse: FloatParamHandle

        self.setattr_param(
            "imaging_clock_pulse_detuning",
            FloatParam,
            "Detuning for the imaging clock pulse",
            default=0.0,
            unit="kHz",
        )
        self.imaging_clock_pulse_detuning: FloatParamHandle

    @kernel
    def do_first_pulse(self):
        self.do_pulse()
        delay(self.delay_clock_after_first_pulse.get())
        self.clock_down_dds.set(
            frequency=self.clock_switch_frequency_handle.get()
            + self.imaging_clock_pulse_detuning.get()
            + constants.LMT_DOWN_BEAM_SHIFT,
            amplitude=self.clock_switch_amplitude_handle.get(),
        )

        delay(1e-6)

        # PI PULSE

        self.clock_down_dds.sw.on()
        delay(constants.CLOCK_DOWN_PI_TIME)
        self.clock_down_dds.sw.off()


class SingleImageNormalisedFastKineticsDoubleTrapInterferometryBase(
    SingleImageNormalisedFastKineticsDoubleTrapBase
):
    # TODO: IS THIS REALLY INTERFEROMETRY?
    def time_dropped_before_first_pulse(self):

        # Compensate for the drop under gravity in the excited cloud relative to
        # the ground cloud.
        #
        # TODO: This logic uses values from constants but these are defaults and
        # might be overridden by the user. If they do this, this calculation
        # will be wrong. It does this because this fragment is configured in
        # build_fragment where parameter values are not yet set. This ought to
        # be updated.

        return (
            constants.SHELVING_PULSE_CLEAROUT_DURATION
            + constants.CLOCK_SHELVING_PULSE_TIME
            + 2 * constants.CLOCK_PI_TIME
            + 2 * constants.DELAY_BETWEEN_INTERFEROMETRY_PULSES
        )

    def host_setup(self):
        super().host_setup()

        # Add checks to catch varied parameters which would cause the above
        # gravity calculations to fail. This is horrible code because it a)
        # relies on classes that this one does not inherit from and b) it should
        # just calculate this properly, not throw error when it's wrong. I'm so
        # sorry, time is just too short to do this properly right now.
        handles_and_default_vals = [
            (
                "shelving_pulse_clearout_duration",
                constants.SHELVING_PULSE_CLEAROUT_DURATION,
            ),
            ("shelving_pulse_time", constants.CLOCK_SHELVING_PULSE_TIME),
            ("spectroscopy_pulse_time", constants.CLOCK_PI_TIME),
            (
                "delay_between_interferometry_pulses",
                constants.DELAY_BETWEEN_INTERFEROMETRY_PULSES,
            ),
        ]

        for handle_name, default_val in handles_and_default_vals:
            if not hasattr(self, handle_name):
                logger.warning(
                    "NormaliseXXODT readout is applying gravity corrections assuming that you're doing "
                    "slicing but you're not, so the gravity corrections will be wrong. "
                    "Specifically the %s parameter is not present.",
                    handle_name,
                )
            else:
                val = getattr(self, handle_name).get()

                diff = val - default_val
                if abs(diff) / default_val > 1e-6:
                    logger.warning(
                        "NormaliseXXODT readout is applying gravity corrections based on the "
                        "default parameter value of %s = %s, but you have set it to %s so the "
                        "excited state ROI will be in the wrong place.",
                        handle_name,
                        default_val,
                        val,
                    )


class SingleImageNormalisedFastKineticsDoubleTrapSpectroscopyBase(
    SingleImageNormalisedFastKineticsDoubleTrapBase
):

    def time_dropped_before_first_pulse(self):
        return (
            constants.SHELVING_PULSE_CLEAROUT_DURATION
            + constants.CLOCK_SHELVING_PULSE_TIME
            + constants.CLOCK_PI_TIME
            + constants.DELAY_AFTER_CLOCK_SPECTROSCOPY
        )

    def host_setup(self):

        handles_and_default_vals = [
            (
                "shelving_pulse_clearout_duration",
                constants.SHELVING_PULSE_CLEAROUT_DURATION,
            ),
            ("shelving_pulse_time", constants.CLOCK_SHELVING_PULSE_TIME),
            ("spectroscopy_pulse_time", constants.CLOCK_PI_TIME),
            ("delay_after_spectroscopy", constants.DELAY_AFTER_CLOCK_SPECTROSCOPY),
        ]

        for handle_name, default_val in handles_and_default_vals:
            if not hasattr(self, handle_name):
                logger.warning(
                    "NormaliseXXODT readout is applying gravity corrections assuming that you're doing "
                    "slicing but you're not, so the gravity corrections will be wrong. "
                    "Specifically the %s parameter is not present.",
                    handle_name,
                )
            else:
                val = getattr(self, handle_name).get()

                diff = val - default_val
                if abs(diff) / default_val > 1e-6:
                    logger.warning(
                        "NormaliseXXODT readout is applying gravity corrections based on the "
                        "default parameter value of %s = %s, but you have set it to %s so the "
                        "excited state ROI will be in the wrong place.",
                        handle_name,
                        default_val,
                        val,
                    )
