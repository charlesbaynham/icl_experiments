"""
Mixin bases for single-image normalised fast kinetics readout with the Andor
camera. Used only in single_image_normalised_fast_kinetics.py, but split out here for organisation
"""

import abc
import logging

import numpy as np
from artiq.language import at_mu
from artiq.language import delay
from artiq.language import host_only
from artiq.language import kernel
from artiq.language import now_mu
from artiq.language import portable
from artiq.language import rpc
from artiq.master.scheduler import Scheduler
from artiq_influx_generic import InfluxController
from ndscan.experiment import FloatChannel
from ndscan.experiment.parameters import FloatParam
from ndscan.experiment.parameters import FloatParamHandle
from ndscan.experiment.parameters import IntParam
from ndscan.experiment.parameters import IntParamHandle

from repository.lib import constants
from repository.lib.experiment_templates.mixins.andor_imaging.imaging_base import (
    AndorImagingBase,
)
from repository.lib.experiment_templates.mixins.clock_spectroscopy import (
    ClockSpectroscopyBase,
)
from repository.lib.fragments.cameras.andor_camera import FastKineticsCameraConfig

logger = logging.getLogger(__name__)
ANDOR_FK_G_BG_CORR_DATASET = "g_bg_corrected"
ANDOR_FK_E_BG_CORR_DATASET = "e_bg_corrected"


# %% Utility functions


def _single_trap_roi_block(x0, y0, x1, y1, offset, step, bg_width):
    """Build the six-ROI single-trap layout as a NumPy array.

    The returned block contains, in order, the ground-state signal ROI, the
    excited-state signal ROI, then left and right background ROIs for each
    signal. Production code does not call this helper directly because the
    camera-config path runs under ARTIQ ``@portable`` constraints and cannot
    safely allocate and return a fresh NumPy array there. It is kept as a
    host-side reference implementation and as a focused test hook for the ROI
    geometry.
    """
    return np.array(
        [
            [x0, y0 - offset, x1, y1 - offset],
            [x0, y0 + step - offset, x1, y1 + step - offset],
            [x0 - bg_width, y0 - offset, x0, y1 - offset],
            [x0 - bg_width, y0 + step - offset, x0, y1 + step - offset],
            [x1, y0 - offset, x1 + bg_width, y1 - offset],
            [x1, y0 + step - offset, x1 + bg_width, y1 + step - offset],
        ],
        dtype=np.int32,
    )


@portable
def _background_correct_trap_block(sums, areas, start_index):
    """Return background-corrected ground and excited counts for one trap.

    ``start_index`` selects a six-ROI block laid out as signal-ground,
    signal-excited, then the left and right background ROIs for each signal.
    The background sums are scaled by ROI area so the correction matches the
    signal ROI area before subtraction.
    """
    ground_signal_index = start_index
    excited_signal_index = start_index + 1
    ground_background_indices = (start_index + 2, start_index + 4)
    excited_background_indices = (start_index + 3, start_index + 5)

    ground_norm_factor = areas[ground_signal_index] / (
        areas[ground_background_indices[0]] + areas[ground_background_indices[1]]
    )
    excited_norm_factor = areas[excited_signal_index] / (
        areas[excited_background_indices[0]] + areas[excited_background_indices[1]]
    )

    ground_atom_number = sums[ground_signal_index] - ground_norm_factor * (
        sums[ground_background_indices[0]] + sums[ground_background_indices[1]]
    )
    excited_atom_number = sums[excited_signal_index] - excited_norm_factor * (
        sums[excited_background_indices[0]] + sums[excited_background_indices[1]]
    )

    return ground_atom_number, excited_atom_number


@portable
def _copy_trap_roi_block(
    roi_buffer, start_index, x0, y0, x1, y1, offset, step, bg_width
):
    """Write the six-ROI single-trap layout into a preallocated ROI buffer.

    This mirrors :func:`_single_trap_roi_block`, but writes element-by-element
    into an existing buffer so it can be used from ARTIQ ``@portable`` code.
    The camera-config classes use this helper to avoid allocating a fresh array
    while still sharing one ROI layout definition.
    """
    roi_buffer[start_index + 0][0] = x0
    roi_buffer[start_index + 0][1] = y0 - offset
    roi_buffer[start_index + 0][2] = x1
    roi_buffer[start_index + 0][3] = y1 - offset

    roi_buffer[start_index + 1][0] = x0
    roi_buffer[start_index + 1][1] = y0 + step - offset
    roi_buffer[start_index + 1][2] = x1
    roi_buffer[start_index + 1][3] = y1 + step - offset

    roi_buffer[start_index + 2][0] = x0 - bg_width
    roi_buffer[start_index + 2][1] = y0 - offset
    roi_buffer[start_index + 2][2] = x0
    roi_buffer[start_index + 2][3] = y1 - offset

    roi_buffer[start_index + 3][0] = x0 - bg_width
    roi_buffer[start_index + 3][1] = y0 + step - offset
    roi_buffer[start_index + 3][2] = x0
    roi_buffer[start_index + 3][3] = y1 + step - offset

    roi_buffer[start_index + 4][0] = x1
    roi_buffer[start_index + 4][1] = y0 - offset
    roi_buffer[start_index + 4][2] = x1 + bg_width
    roi_buffer[start_index + 4][3] = y1 - offset

    roi_buffer[start_index + 5][0] = x1
    roi_buffer[start_index + 5][1] = y0 + step - offset
    roi_buffer[start_index + 5][2] = x1 + bg_width
    roi_buffer[start_index + 5][3] = y1 + step - offset


# %% Camera config classes


class SingleFKSingleTrapConfig(FastKineticsCameraConfig):
    """
    Config for single-image normalised fast-kinetics readout with one trap.

    Creates 2 signal ROIs (ground + excited state) plus 4 background ROIs
    (left+right of each signal), for 6 total.
    """

    num_andor_images = 2
    num_images_per_series = 2
    num_grabber_rois = 6
    num_grabber_readouts = 1
    fast_kinetics_num_shots = 2

    fast_kinetics_height_default = constants.ANDOR_FAST_KINETICS_HEIGHT
    fast_kinetics_offset_default = constants.ANDOR_FAST_KINETICS_OFFSET

    def build_fragment(self, x0, y0, x1, y1, bg_width, excited_shift=0):
        super().build_fragment()

        self.setattr_param(
            "roi_x0",
            IntParam,
            "Grabber ROI x0",
            default=x0,
            min=0,
            max=512,
        )
        self.roi_x0: IntParamHandle
        self.setattr_param(
            "roi_y0",
            IntParam,
            "Grabber ROI y0",
            default=y0,
            min=0,
            max=1024,
        )
        self.roi_y0: IntParamHandle
        self.setattr_param(
            "roi_x1",
            IntParam,
            "Grabber ROI x1",
            default=x1,
            min=0,
            max=512,
        )
        self.roi_x1: IntParamHandle
        self.setattr_param(
            "roi_y1",
            IntParam,
            "Grabber ROI y1",
            default=y1,
            min=0,
            max=1024,
        )
        self.roi_y1: IntParamHandle

        self.setattr_param(
            "bg_width",
            IntParam,
            "Background ROI width (pixels)",
            default=bg_width,
            min=0,
            max=512,
        )
        self.bg_width: IntParamHandle

        self._excited_shift = np.int32(excited_shift)
        self.roi_buffer = np.zeros((self.num_grabber_rois, 4), dtype=np.int32)

    @portable
    def get_rois(self):
        height = self.fast_kinetics_height.get()
        offset = self.fast_kinetics_offset.get()
        x0 = self.roi_x0.get()
        y0 = self.roi_y0.get()
        x1 = self.roi_x1.get()
        y1 = self.roi_y1.get()
        bg_width = self.bg_width.get()
        step = height - self._excited_shift

        _copy_trap_roi_block(
            roi_buffer=self.roi_buffer,
            start_index=0,
            x0=x0,
            y0=y0,
            x1=x1,
            y1=y1,
            offset=offset,
            step=step,
            bg_width=bg_width,
        )

        return self.roi_buffer


class SingleFKDoubleTrapConfig(FastKineticsCameraConfig):
    """
    Config for single-image normalised fast-kinetics readout with two traps.

    Creates 4 signal ROIs (ground/excited x forward/backward) plus 8 background
    ROIs, for 12 total. ROIs 0..5 are the "top trap" (backward ROIs), ROIs 6..11
    are the "bottom trap" (forward ROIs); within each set the layout matches
    SingleFKSingleTrapConfig.
    """

    num_andor_images = 2
    num_images_per_series = 2
    num_grabber_rois = 12
    num_grabber_readouts = 1
    fast_kinetics_num_shots = 2

    fast_kinetics_height_default = constants.ANDOR_FAST_KINETICS_HEIGHT
    fast_kinetics_offset_default = constants.ANDOR_FAST_KINETICS_OFFSET

    def build_fragment(
        self,
        fwd_x0,
        fwd_y0,
        fwd_x1,
        fwd_y1,
        bwd_x0,
        bwd_y0,
        bwd_x1,
        bwd_y1,
        bg_width,
        excited_shift=0,
    ):
        super().build_fragment()

        self.setattr_param(
            "fwd_roi_x0",
            IntParam,
            "Forward trap grabber ROI x0",
            default=fwd_x0,
            min=0,
            max=512,
        )
        self.fwd_roi_x0: IntParamHandle
        self.setattr_param(
            "fwd_roi_y0",
            IntParam,
            "Forward trap grabber ROI y0",
            default=fwd_y0,
            min=0,
            max=1024,
        )
        self.fwd_roi_y0: IntParamHandle
        self.setattr_param(
            "fwd_roi_x1",
            IntParam,
            "Forward trap grabber ROI x1",
            default=fwd_x1,
            min=0,
            max=512,
        )
        self.fwd_roi_x1: IntParamHandle
        self.setattr_param(
            "fwd_roi_y1",
            IntParam,
            "Forward trap grabber ROI y1",
            default=fwd_y1,
            min=0,
            max=1024,
        )
        self.fwd_roi_y1: IntParamHandle

        self.setattr_param(
            "bwd_roi_x0",
            IntParam,
            "Backward trap grabber ROI x0",
            default=bwd_x0,
            min=0,
            max=512,
        )
        self.bwd_roi_x0: IntParamHandle
        self.setattr_param(
            "bwd_roi_y0",
            IntParam,
            "Backward trap grabber ROI y0",
            default=bwd_y0,
            min=0,
            max=1024,
        )
        self.bwd_roi_y0: IntParamHandle
        self.setattr_param(
            "bwd_roi_x1",
            IntParam,
            "Backward trap grabber ROI x1",
            default=bwd_x1,
            min=0,
            max=512,
        )
        self.bwd_roi_x1: IntParamHandle
        self.setattr_param(
            "bwd_roi_y1",
            IntParam,
            "Backward trap grabber ROI y1",
            default=bwd_y1,
            min=0,
            max=1024,
        )
        self.bwd_roi_y1: IntParamHandle

        self.setattr_param(
            "bg_width",
            IntParam,
            "Background ROI width (pixels)",
            default=bg_width,
            min=0,
            max=512,
        )
        self.bg_width: IntParamHandle

        self._excited_shift = np.int32(excited_shift)
        self.roi_buffer = np.zeros((self.num_grabber_rois, 4), dtype=np.int32)

    @portable
    def get_rois(self):
        height = self.fast_kinetics_height.get()
        offset = self.fast_kinetics_offset.get()
        bg_width = self.bg_width.get()
        step = height - self._excited_shift

        # Top trap = backward ROIs at indices 0..5
        bx0 = self.bwd_roi_x0.get()
        by0 = self.bwd_roi_y0.get()
        bx1 = self.bwd_roi_x1.get()
        by1 = self.bwd_roi_y1.get()

        _copy_trap_roi_block(
            roi_buffer=self.roi_buffer,
            start_index=0,
            x0=bx0,
            y0=by0,
            x1=bx1,
            y1=by1,
            offset=offset,
            step=step,
            bg_width=bg_width,
        )

        # Bottom trap = forward ROIs at indices 6..11
        fx0 = self.fwd_roi_x0.get()
        fy0 = self.fwd_roi_y0.get()
        fx1 = self.fwd_roi_x1.get()
        fy1 = self.fwd_roi_y1.get()

        _copy_trap_roi_block(
            roi_buffer=self.roi_buffer,
            start_index=6,
            x0=fx0,
            y0=fy0,
            x1=fx1,
            y1=fy1,
            offset=offset,
            step=step,
            bg_width=bg_width,
        )

        return self.roi_buffer


# %% Mixin bases


class SingleImageNormalisedBase(AndorImagingBase):

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
        self.andor_camera_config.bind_param(
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

    @abc.abstractmethod
    def get_andor_camera_config_hook(self):
        """
        Build the AndorCameraConfig for this experiment.

        Subclasses must override this and return a config (typically built via
        ``setattr_fragment``).
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


class SingleImageNormalisedSingleTrapBase(SingleImageNormalisedBase):
    """
    Implements normalised readout using a single image for a :py:class:`~RedMOTWithExperimentBase`
    experiment.

    This mixin base uses the Andor camera to take one fast kinetics series with two images and creates a
    ResultChannels for normalised state readout. The two images in the fast kinetics series images atoms that starts in (i)
    the ground state, and (ii) the excited state.
    The normalised image is then calculated by subtracting the counts of the signal ROI with an average background count that is calculated as followed:
    Consider two background ROIs with the same height as the signal ROI and a width of 50 pixels; the two images are placed immediately to the left and right of the signal ROI.
    The total sum of background ROI counts is divided by the number of pixels in the background ROI and multiplied by the number of pixels in the signal ROI to get the average background across the entire signal ROI.
    Finally this background count is subtracted from the total signal ROI to get a normalised value.

    Variant mixins based on this class are expected to reimplement get_andor_camera_config_hook
    and/or fast_kinetics_default_height and fast_kinetics_default_offset as needed.

    This is a mixin - see the documentation for :mod:`~.red_mot_experiment` for
    details.

    NOTE I HAVE OMITTED THE CODE FOR THE GAUSSIAN FIT BECAUSE I AM LAZY - Dillen

    Kernel hooks used (multiple mixins cannot use the same hooks):

    * :meth:`~do_imaging_hook_andor`
    * :meth:`~process_andor_data_hook`
    * :meth:`~update_andor_monitor_hook`
    """

    def get_andor_camera_config_hook(self) -> SingleFKSingleTrapConfig:
        # TODO: This is the single trap mapping; the double trap variant has
        # bg_width and excited_shift swapped -- investigate later.
        f = self.setattr_fragment(
            "andor_camera_config",
            SingleFKSingleTrapConfig,
            x0=constants.ANDOR_ROI_X0,
            y0=constants.ANDOR_ROI_Y0,
            x1=constants.ANDOR_ROI_X1,
            y1=constants.ANDOR_ROI_Y1,
            bg_width=self.calculate_gravitational_drop(),
            excited_shift=constants.ROI_SHIFT_EXCITED_STATE,
        )
        self.andor_camera_config: SingleFKSingleTrapConfig
        return f

    def fast_kinetics_setup_results(self):
        self.setattr_result("excitation_fraction", FloatChannel)
        self.setattr_result("atom_number", FloatChannel)
        self.setattr_result("ground_atom_number", FloatChannel)
        self.setattr_result("excited_atom_number", FloatChannel)

        self.excitation_fraction: FloatChannel
        self.atom_number: FloatChannel
        self.ground_atom_number: FloatChannel
        self.excited_atom_number: FloatChannel

    @host_only
    def get_monitor_rois(self):
        """
        Get the default ROIs for the Andor monitors
        """
        return np.array(self.andor_camera_config.get_rois()[0:3]).tolist()

    @kernel
    def process_grabber_data_hook(self, sums, means):
        # The normalisation factor is the ratio of the number of pixels in the background to signal ROIs. Since we have coerced the background ROIs to have the same height as the signal ROIs, this is just 2x the ratio of the widths (since we have two background ROIs, one on either side of the signal ROI).
        rois = self.andor_camera_config.get_rois()
        areas = [np.int32(0)] * 6
        for i in range(6):
            areas[i] = self.get_roi_area(rois[i])

        # ROI 0     : Ground state signal ROI
        # ROI 1     : Excited state signal ROI
        # ROI 2 & 6 : Ground state background ROI
        # ROI 3 & 5 : Excited state background ROI

        # TODO : This BG subtraction method is common to both of the double and single trap so in principle should be
        # in the top base class, but I need to figure out how the ROIs are defined.

        atom_num_1, atom_num_2 = _background_correct_trap_block(
            sums=sums,
            areas=areas,
            start_index=0,
        )
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


class SingleImageNormalisedDoubleTrapBase(SingleImageNormalisedBase):
    """
    Implements normalised readout for a :py:class:`~RedMOTWithExperimentBase`
    experiment

    This mixin base uses the Andor camera to two fast kinetics series with two images each and create
    ResultChannels for normalised state readout. The first series contains atoms that starts in (i)
    the ground state, and (ii) the excited state. The second series reproduces the conditions of the first,
    with a long delay to clear out atoms.

    Variant mixins based on this class are expected to reimplement get_andor_camera_config_hook
    and/or fast_kinetics_default_height and fast_kinetics_default_offset as needed.

    This is a mixin - see the documentation for :mod:`~.red_mot_experiment` for
    details.

    Kernel hooks used (multiple mixins cannot use the same hooks):

    * :meth:`~do_imaging_hook_andor`
    * :meth:`~process_andor_data_hook`
    * :meth:`~update_andor_monitor_hook`
    """

    def get_andor_camera_config_hook(self) -> SingleFKDoubleTrapConfig:
        f = self.setattr_fragment(
            "andor_camera_config",
            SingleFKDoubleTrapConfig,
            fwd_x0=constants.ANDOR_ROI_DIPOLE_TRAP_FORWARD_X0,
            fwd_y0=constants.ANDOR_ROI_DIPOLE_TRAP_FORWARD_Y0,
            fwd_x1=constants.ANDOR_ROI_DIPOLE_TRAP_FORWARD_X1,
            fwd_y1=constants.ANDOR_ROI_DIPOLE_TRAP_FORWARD_Y1,
            bwd_x0=constants.ANDOR_ROI_DIPOLE_TRAP_BACKWARD_X0,
            bwd_y0=constants.ANDOR_ROI_DIPOLE_TRAP_BACKWARD_Y0,
            bwd_x1=constants.ANDOR_ROI_DIPOLE_TRAP_BACKWARD_X1,
            bwd_y1=constants.ANDOR_ROI_DIPOLE_TRAP_BACKWARD_Y1,
            bg_width=constants.ANDOR_SINGLE_FAST_KINETICS_BACKGROUND_ROI_WIDTH,
            excited_shift=self.calculate_gravitational_drop(),
        )
        self.andor_camera_config: SingleFKDoubleTrapConfig
        return f  # type: ignore

    def fast_kinetics_setup_results(self):
        self.setattr_result("excitation_fraction_forward", FloatChannel)
        self.setattr_result("atom_number_forward", FloatChannel)

        self.setattr_result("excitation_fraction_backward", FloatChannel)
        self.setattr_result("atom_number_backward", FloatChannel)

        self.setattr_result("atom_number_imbalance", FloatChannel)
        self.setattr_result("atom_number_total", FloatChannel)

        # Keep the double-trap output focused on per-trap excitation fractions,
        # per-trap atom numbers, imbalance, and total population.

        self.excitation_fraction_forward: FloatChannel
        self.atom_number_forward: FloatChannel
        self.excitation_fraction_backward: FloatChannel
        self.atom_number_backward: FloatChannel
        self.atom_number_imbalance: FloatChannel
        self.atom_number_total: FloatChannel

    @kernel
    def process_grabber_data_hook(self, sums, means):
        # The normalisation factor is the ratio of the number of pixels in the background to signal ROIs. Since we have coerced the background ROIs to have the same height as the signal ROIs, this is just 2x the ratio of the widths (since we have two background ROIs, one on either side of the signal ROI).
        rois = self.andor_camera_config.get_rois()
        areas = [np.int32(0)] * 12
        for i in range(12):
            areas[i] = self.get_roi_area(rois[i])

        # TODO Check that the indices are correct

        atom_number_ground_top, atom_number_excited_top = (
            _background_correct_trap_block(sums=sums, areas=areas, start_index=0)
        )
        atom_number_ground_bottom, atom_number_excited_bottom = (
            _background_correct_trap_block(sums=sums, areas=areas, start_index=6)
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


# %% Gravity compensation mixins


class DroptimeInterferometryMixin(SingleImageNormalisedBase):
    """
    Set up ROI drops for interferometry

    This class should not need to exist - it's here to tell the imaging setup
    how long the atoms are falling for. It's therefore custom for a given
    experiment (interferometry) in this case and fragile. We will get rid of it
    soon using the code on the `icl_experiments.dma_lmt_abc` branch.
    """

    def time_dropped_before_first_pulse(self):
        """
        Compensate for the drop under gravity in the excited cloud relative to
        the ground cloud.
        """

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


class DroptimeSpectroscopyMixin(SingleImageNormalisedBase):
    """
    Set up ROI drops for spectroscopy

    This class should not need to exist - it's here to tell the imaging setup
    how long the atoms are falling for. It's therefore custom for a given
    experiment (interferometry) in this case and fragile. We will get rid of it
    soon using the code on the `icl_experiments.dma_lmt_abc` branch.
    """

    def time_dropped_before_first_pulse(self):
        """
        Compensate for the drop under gravity in the excited cloud relative to
        the ground cloud.
        """

        # TODO: This logic uses values from constants but these are defaults and
        # might be overridden by the user. If they do this, this calculation
        # will be wrong. It does this because this fragment is configured in
        # build_fragment where parameter values are not yet set. This ought to
        # be updated.

        return (
            constants.SHELVING_PULSE_CLEAROUT_DURATION
            + constants.CLOCK_SHELVING_PULSE_TIME
            + constants.CLOCK_PI_TIME
        )


# %% Repumping mixins


class RepumpingWith679Mixin(SingleImageNormalisedBase):
    """
    Repumping-based normalisation for SingleImage imaging
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


class RepumpingWithClockMixin(
    SingleImageNormalisedSingleTrapBase,
    SingleImageNormalisedBase,
    ClockSpectroscopyBase,
):
    """
    Repumping with a clock pulse for SingleImage imaging
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

        self.clock_down_dds.sw.on()
        delay(constants.CLOCK_DOWN_PI_TIME)
        self.clock_down_dds.sw.off()
