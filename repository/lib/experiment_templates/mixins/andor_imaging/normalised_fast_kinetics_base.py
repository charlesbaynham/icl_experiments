import logging
from typing import List

import numpy as np
from artiq.language import at_mu
from artiq.language import delay
from artiq.language import host_only
from artiq.language import kernel
from artiq.language import now_mu
from artiq.language import rpc
from ndscan.experiment import FloatChannel
from ndscan.experiment.parameters import FloatParam
from ndscan.experiment.parameters import FloatParamHandle

from repository.lib import constants
from repository.lib.experiment_templates.mixins.andor_imaging.imaging_base import (
    AndorImagingBase,
)
from repository.lib.experiment_templates.mixins.andor_imaging.imaging_base import (
    fit_2d_gaussian,
)
from repository.lib.fragments.cameras.andor_camera import AndorCameraControl

logger = logging.getLogger(__name__)

ANDOR_FK_G_BG_CORR_DATASET = "g_bg_corrected"
ANDOR_FK_E_BG_CORR_DATASET = "e_bg_corrected"


def calculate_grabber_rois(
    fast_kinetics_height, fast_kinetics_offset, num_images, x0, y0, x1, y1
):
    """
    Given an ROI (x0, y0, x1, y1) on the full image, calculate the required ROI
    when in fast kinetics mode.

    Returns a list of ROIs in (x0, y0, x1, y1) format.

    TODO: For normalised clock readout, which may need repumping for several ms
    between 461 flu pulses, we should write a more sophisticated ROI calculator to
    account for the cloud falling under gravity.
    """

    logger.debug(
        "fast_kinetics_height, fast_kinetics_offset, num_images, x0, y0, x1, y1",
        (fast_kinetics_height, fast_kinetics_offset, num_images, x0, y0, x1, y1),
    )

    if y1 > fast_kinetics_height + fast_kinetics_offset:
        raise ValueError(
            "The fast kinetics region is not large enough to cover the full ROI"
        )

    return [
        [
            x0,
            y0 + i * fast_kinetics_height - fast_kinetics_offset,
            x1,
            y1 + i * fast_kinetics_height - fast_kinetics_offset,
        ]
        for i in range(num_images)
    ]


class NormalisedFastKineticsBase(AndorImagingBase):
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

    num_andor_images = 4
    num_grabber_readouts = 2
    num_grabber_rois = 2
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

        self.setattr_param(
            "delay_before_bg_img",
            FloatParam,
            "Delay before bg image series",
            default=400e-3,
            unit="ms",
        )
        self.delay_before_bg_img: FloatParamHandle

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

    def setup_gauss_fit_results(self):
        self.amps: List[FloatChannel] = []
        self.x_pos: List[FloatChannel] = []
        self.y_pos: List[FloatChannel] = []
        self.sigmas_x: List[FloatChannel] = []
        self.sigmas_y: List[FloatChannel] = []
        for i in range(int(self.num_grabber_rois / self.num_grabber_readouts)):
            for j in ("ground", "excited"):
                self.amps.append(
                    self.setattr_result(
                        f"amp_{i}_{j}", FloatChannel, display_hints={"priority": -1}
                    )
                )
                self.x_pos.append(
                    self.setattr_result(
                        f"x_pos_{i}_{j}", FloatChannel, display_hints={"priority": -1}
                    )
                )
                self.y_pos.append(
                    self.setattr_result(
                        f"y_pos_{i}_{j}", FloatChannel, display_hints={"priority": -1}
                    )
                )
                self.sigmas_x.append(
                    self.setattr_result(
                        f"sigma_x_{i}_{j}", FloatChannel, display_hints={"priority": -1}
                    )
                )
                self.sigmas_y.append(
                    self.setattr_result(
                        f"sigma_y_{i}_{j}", FloatChannel, display_hints={"priority": -1}
                    )
                )

    def get_grabber_roi_defaults(self):
        return calculate_grabber_rois(
            fast_kinetics_height=self.fast_kinetics_height_default,
            fast_kinetics_offset=self.fast_kinetics_offset_default,
            num_images=self.num_images_per_series,
            x0=constants.ANDOR_ROI_X0,
            y0=constants.ANDOR_ROI_Y0,
            x1=constants.ANDOR_ROI_X1,
            y1=constants.ANDOR_ROI_Y1,
        )

    @kernel
    def do_imaging_hook_andor(self):
        """
        Hook for the imaging sequence. This hook runs after the spectroscopy
        etc. is completed, and should handle imaging with the Andor camera.
        """
        self.do_first_series()
        t_post_mu = now_mu()
        self.post_first_series()  # call rpc to get images, start next acquisition
        at_mu(t_post_mu)
        delay(self.delay_before_bg_img.get())
        self.pre_second_series()
        self.do_second_series()
        self.post_second_series()  # call rpc to get images

    @kernel
    def do_first_series(self):
        # Image ground state atoms
        t_start_mu = now_mu()
        self.do_first_pulse()

        # Image excited state atoms
        at_mu(t_start_mu)
        delay(self.delay_between_imaging_pulses.get())
        self.do_second_pulse()

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
    def pre_second_series(self):
        """
        eg turn on beams for some time
        must not advance the timeline
        """

    @kernel
    def do_second_series(self):
        # second verse, same as the first
        self.do_first_series()

    @kernel
    def post_second_series(self):
        pass

    @kernel
    def do_first_pulse(self):
        # Normal fluorescence pulse at now_mu() + camera trigger, pre-empted by
        # the time required to shift one Fast Kinetics region + a
        # pre_trigger_delay
        self.do_pulse()

    @kernel
    def do_second_pulse(self):
        self.do_just_a_fluorescence_pulse()

    @kernel
    def do_just_a_fluorescence_pulse(self):
        # Just a fluorescence pulse - the camera has already been triggered and handles its own timings
        self.fluorescence_pulse.do_imaging_pulse(ignore_final_shutters=True)

    @kernel
    def process_grabber_data_hook(self, sums, means):
        atom_number = sums[0] + sums[1] - sums[2] - sums[3]

        if atom_number == 0:
            self.excitation_fraction.push(0.0)
        else:
            self.excitation_fraction.push((sums[1] - sums[3]) / atom_number)

        self.atom_number.push(atom_number)

    @host_only
    def process_andor_image_hook(self, images: np.array):
        super().process_andor_image_hook(images)
        ground_bg_corrected = images[0].astype(int) - images[2].astype(int)
        excited_bg_corrected = images[1].astype(int) - images[3].astype(int)
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

    @host_only
    def do_gauss_fit_hook(self, img_array: np.ndarray):
        ground_bg_corrected = img_array[0].astype(int) - img_array[2].astype(int)
        excited_bg_corrected = img_array[1].astype(int) - img_array[3].astype(int)
        for i in range(int(self.num_grabber_rois / self.num_grabber_readouts)):
            for j, image in enumerate([ground_bg_corrected, excited_bg_corrected]):
                grabber_idx = int(2 * i)

                sliced_image, offsets = self.andor_camera_control.slice_from_roi_params(
                    image, grabber_idx
                )
                popt = fit_2d_gaussian(sliced_image, offsets)
                self.push_gauss_fit_pars(popt, int(2 * i + j))


class NormalisedFastKineticsRepumpedMixin(NormalisedFastKineticsBase):
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
