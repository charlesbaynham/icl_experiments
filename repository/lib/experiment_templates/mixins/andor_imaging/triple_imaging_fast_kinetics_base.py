import logging

from artiq.language import at_mu
from artiq.language import delay
from artiq.language import kernel
from artiq.language import now_mu
from ndscan.experiment import FloatChannel
from ndscan.experiment.parameters import FloatParam
from ndscan.experiment.parameters import FloatParamHandle

from repository.lib import constants
from repository.lib.experiment_templates.mixins.andor_imaging.imaging_base import (
    AndorImagingBase,
)
from repository.lib.fragments.cameras.andor_camera import AndorCameraControl

logger = logging.getLogger(__name__)


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


class TripleImageFastKineticsBase(AndorImagingBase):
    """
    Implements normalised readout for a :py:class:`~RedMOTWithExperiment`
    experiment

    This mixin base uses the Andor camera to take three images and create
    ResultChannels for normalised state readout, assuming that the first image
    is ground-state atoms, the second one is excited state and the third is
    background (i.e. no atoms at all).

    Variant mixins based on this class are expected to reimplement get_grabber_roi_defaults
    and/or fast_kinetics_default_height and fast_kinetics_default_offset as needed.

    This is a mixin - see the documentation for :mod:`~.red_mot_experiment` for
    details.

    Kernel hooks used (multiple mixins cannot use the same hooks):

    * :meth:`~do_imaging_hook_andor`
    * :meth:`~process_andor_data_hook`
    * :meth:`~update_andor_monitor_hook`
    """

    num_andor_images = 3
    num_grabber_readouts = 1
    num_grabber_rois = 3
    fast_kinetics_height_default = constants.ANDOR_FAST_KINETICS_HEIGHT
    fast_kinetics_offset_default = constants.ANDOR_FAST_KINETICS_OFFSET

    def build_fragment(self):
        super().build_fragment()

        self.setattr_param(
            "delay_between_imaging_pulses",
            FloatParam,
            "Total time between the starts of the three fluorescence pulses",
            default=3e-3,
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

        self.fast_kinetics_setup_results()

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
            fast_kinetics_num_shots=3,
        )
        self.andor_camera_control: AndorCameraControl

        self.hook_setup_andor_results()

    def get_grabber_roi_defaults(self):  # FIXME
        return calculate_grabber_rois(
            fast_kinetics_height=self.fast_kinetics_height_default,
            fast_kinetics_offset=self.fast_kinetics_offset_default,
            num_images=self.num_grabber_rois,
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

        # Image ground state atoms
        t_start_mu = now_mu()
        self.do_first_pulse()

        # Image excited state atoms
        at_mu(t_start_mu)
        delay(self.delay_between_imaging_pulses.get())
        self.do_second_pulse()

        # Take background measurement
        at_mu(t_start_mu)
        delay(2 * self.delay_between_imaging_pulses.get())
        self.do_third_pulse()

    @kernel
    def do_first_pulse(self):
        # Normal fluorescence pulse at now_mu() + camera trigger, pre-empted by
        # the time required to shift one Fast Kinetics region + a
        # pre_trigger_delay
        self.do_pulse()

    @kernel
    def do_just_a_fluorescence_pulse(self):
        # Just a fluorescence pulse - the camera has already been triggered and handles its own timings
        self.fluorescence_pulse.do_imaging_pulse(ignore_final_shutters=True)

    @kernel
    def do_second_pulse(self):
        self.do_just_a_fluorescence_pulse()

    @kernel
    def do_third_pulse(self):
        self.do_just_a_fluorescence_pulse()

    @kernel
    def process_grabber_data_hook(self, sums, means):
        atom_number = sums[0] + sums[1] - 2 * sums[2]

        if atom_number == 0:
            self.excitation_fraction.push(0.0)
        else:
            self.excitation_fraction.push((sums[1] - sums[2]) / atom_number)

        self.atom_number.push(atom_number)
