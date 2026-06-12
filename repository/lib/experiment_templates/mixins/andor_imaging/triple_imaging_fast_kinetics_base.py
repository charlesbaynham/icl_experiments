import logging

import numpy as np
from artiq.language import at_mu
from artiq.language import delay
from artiq.language import kernel
from artiq.language import now_mu
from artiq.language import portable
from ndscan.experiment import FloatChannel
from ndscan.experiment.parameters import FloatParam
from ndscan.experiment.parameters import FloatParamHandle
from ndscan.experiment.parameters import IntParam
from ndscan.experiment.parameters import IntParamHandle

from repository.lib import constants
from repository.lib.experiment_templates.mixins.andor_imaging.imaging_base import (
    AndorImagingBase,
)
from repository.lib.fragments.cameras.andor_camera import FastKineticsCameraConfig

logger = logging.getLogger(__name__)


class TripleFKConfig(FastKineticsCameraConfig):
    """
    Camera config for triple-image fast kinetics readout.

    Takes 3 images per series (ground state, excited state, background),
    producing 3 grabber ROIs with a single grabber readout.
    """

    num_andor_images = 3
    num_images_per_series = 3
    num_grabber_rois = 3
    num_grabber_readouts = 1
    fast_kinetics_num_shots = 3

    fast_kinetics_height = constants.ANDOR_FAST_KINETICS_HEIGHT
    fast_kinetics_offset = constants.ANDOR_FAST_KINETICS_OFFSET

    def build_fragment(self, x0, y0, x1, y1):
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
            default=y0 - self.fast_kinetics_offset,
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
            default=y1 - self.fast_kinetics_offset,
            min=0,
            max=1024,
        )
        self.roi_y1: IntParamHandle

        self.roi_buffer = np.zeros((self.num_grabber_rois, 4), dtype=np.int32)

    @portable
    def get_rois(self):
        height = self.fast_kinetics_height
        x0 = self.roi_x0.get()
        y0_minus_offset = self.roi_y0.get()
        x1 = self.roi_x1.get()
        y1_minus_offset = self.roi_y1.get()

        self.roi_buffer[0][0] = x0
        self.roi_buffer[0][1] = y0_minus_offset
        self.roi_buffer[0][2] = x1
        self.roi_buffer[0][3] = y1_minus_offset
        self.roi_buffer[1][0] = x0
        self.roi_buffer[1][1] = y0_minus_offset + height
        self.roi_buffer[1][2] = x1
        self.roi_buffer[1][3] = y1_minus_offset + height
        self.roi_buffer[2][0] = x0
        self.roi_buffer[2][1] = y0_minus_offset + 2 * height
        self.roi_buffer[2][2] = x1
        self.roi_buffer[2][3] = y1_minus_offset + 2 * height
        return self.roi_buffer


class TripleFKDoubleTrapConfig(FastKineticsCameraConfig):
    """
    Camera config for triple-image fast kinetics readout of two traps (forward + backward).

    Takes 3 images per series (ground state, excited state, background) for each trap,
    producing 6 grabber ROIs (3 forward then 3 backward) with a single grabber readout.
    """

    num_andor_images = 3
    num_images_per_series = 3
    num_grabber_rois = 6
    num_grabber_readouts = 1
    fast_kinetics_num_shots = 3

    fast_kinetics_height = constants.ANDOR_FAST_KINETICS_HEIGHT_DOUBLE_TRAP
    fast_kinetics_offset = constants.ANDOR_FAST_KINETICS_OFFSET_DOUBLE_TRAP

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
            default=fwd_y0 - self.fast_kinetics_offset,
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
            default=fwd_y1 - self.fast_kinetics_offset,
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
            default=bwd_y0 - self.fast_kinetics_offset,
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
            default=bwd_y1 - self.fast_kinetics_offset,
            min=0,
            max=1024,
        )
        self.bwd_roi_y1: IntParamHandle

        self.roi_buffer = np.zeros((self.num_grabber_rois, 4), dtype=np.int32)

    @portable
    def get_rois(self):
        height = self.fast_kinetics_height
        fwd_x0 = self.fwd_roi_x0.get()
        fwd_y0_minus_offset = self.fwd_roi_y0.get()
        fwd_x1 = self.fwd_roi_x1.get()
        fwd_y1_minus_offset = self.fwd_roi_y1.get()
        # Forward trap ROIs: indices 0..2
        self.roi_buffer[0][0] = fwd_x0
        self.roi_buffer[0][1] = fwd_y0_minus_offset
        self.roi_buffer[0][2] = fwd_x1
        self.roi_buffer[0][3] = fwd_y1_minus_offset
        self.roi_buffer[1][0] = fwd_x0
        self.roi_buffer[1][1] = fwd_y0_minus_offset + height
        self.roi_buffer[1][2] = fwd_x1
        self.roi_buffer[1][3] = fwd_y1_minus_offset + height
        self.roi_buffer[2][0] = fwd_x0
        self.roi_buffer[2][1] = fwd_y0_minus_offset + 2 * height
        self.roi_buffer[2][2] = fwd_x1
        self.roi_buffer[2][3] = fwd_y1_minus_offset + 2 * height

        bwd_x0 = self.bwd_roi_x0.get()
        bwd_y0_minus_offset = self.bwd_roi_y0.get()
        bwd_x1 = self.bwd_roi_x1.get()
        bwd_y1_minus_offset = self.bwd_roi_y1.get()
        # Backward trap ROIs: indices 3..5
        self.roi_buffer[3][0] = bwd_x0
        self.roi_buffer[3][1] = bwd_y0_minus_offset
        self.roi_buffer[3][2] = bwd_x1
        self.roi_buffer[3][3] = bwd_y1_minus_offset
        self.roi_buffer[4][0] = bwd_x0
        self.roi_buffer[4][1] = bwd_y0_minus_offset + height
        self.roi_buffer[4][2] = bwd_x1
        self.roi_buffer[4][3] = bwd_y1_minus_offset + height
        self.roi_buffer[5][0] = bwd_x0
        self.roi_buffer[5][1] = bwd_y0_minus_offset + 2 * height
        self.roi_buffer[5][2] = bwd_x1
        self.roi_buffer[5][3] = bwd_y1_minus_offset + 2 * height
        return self.roi_buffer


class TripleImageFastKineticsBase(AndorImagingBase):
    """
    Implements normalised readout for a :py:class:`~RedMOTWithExperimentBase`
    experiment

    This mixin base uses the Andor camera to take three images and create
    ResultChannels for normalised state readout, assuming that the first image
    is ground-state atoms, the second one is excited state and the third is
    background (i.e. no atoms at all).

    This is a mixin - see the documentation for :mod:`~.red_mot_experiment` for
    details.

    Kernel hooks used (multiple mixins cannot use the same hooks):

    * :meth:`~do_imaging_hook_andor`
    * :meth:`~process_andor_data_hook`
    * :meth:`~update_andor_monitor_hook`
    """

    def get_andor_camera_config_hook(self) -> TripleFKConfig:
        f = self.setattr_fragment(
            "andor_camera_config",
            TripleFKConfig,
            x0=constants.ANDOR_ROI_X0,
            y0=constants.ANDOR_ROI_Y0,
            x1=constants.ANDOR_ROI_X1,
            y1=constants.ANDOR_ROI_Y1,
        )
        self.andor_camera_config: TripleFKConfig
        return f

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
        self.andor_camera_config.bind_param(
            "fast_kinetics_time_between_shots",
            self.delay_between_imaging_pulses,
        )

        self.fast_kinetics_setup_results()

    def fast_kinetics_setup_results(self):
        self.setattr_result("excitation_fraction", FloatChannel)
        self.setattr_result("atom_number", FloatChannel)

        self.excitation_fraction: FloatChannel
        self.atom_number: FloatChannel

    @kernel
    def do_imaging_hook_andor(self):
        """
        Hook for the imaging sequence. This hook runs after the spectroscopy
        etc. is completed, and should handle imaging with the Andor camera.
        """

        # Image ground state atoms
        t_start_mu = now_mu()
        self.do_first_pulse()
        self.after_first_imaging_pulse_checkpoint()

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
