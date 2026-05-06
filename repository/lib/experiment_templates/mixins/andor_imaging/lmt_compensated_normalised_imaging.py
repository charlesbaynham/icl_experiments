import logging
from typing import List

import numpy as np
from artiq.language import TList
from artiq.language import kernel
from ndscan.experiment.parameters import IntParam
from ndscan.experiment.parameters import IntParamHandle

from repository.lib import constants
from repository.lib.experiment_templates.mixins.andor_imaging.normalised_fast_kinetics_base import (
    NormalisedFastKineticsClockPulseMixin,
)
from repository.lib.fragments.cameras.andor_camera import AndorCameraConfig

logger = logging.getLogger(__name__)


class LMTCompensatedCameraConfig(AndorCameraConfig):

    def build_fragment(self):
        super().build_fragment()

        self.setattr_param(
            "roi_width",
            IntParam,
            "Width of the ROI (pixels)",
            default=100,  # FIXME put in constants
            min=1,
            max=1024,
        )
        self.roi_width: IntParamHandle

        self.setattr_param(
            "roi_height",
            IntParam,
            "Height of the ROI (pixels)",
            default=100,  # FIXME put in constants
            min=1,
            max=1024,
        )
        self.roi_height: IntParamHandle

        # Kernel variables
        self.gnd_x = 0
        self.gnd_y = 0
        self.excited_x = 0
        self.excited_y = 0

        # Constants
        self.andor_sensor_width = constants.ANDOR_CAMERA_FACTS["sensor_width"]
        self.andor_sensor_height = constants.ANDOR_CAMERA_FACTS["sensor_height"]

        self.kernel_invariants = getattr(self, "kernel_invariants", set())
        self.kernel_invariants.add("andor_sensor_width")
        self.kernel_invariants.add("andor_sensor_height")

    @kernel
    def calculate_atom_positions(
        self,
        t1: np.int64,
        t2: np.int64,
        pulse_times: TList(np.int64),
        pulse_is_up: TList(bool),
    ) -> None:
        """
        Calculate the atom cloud positions based on the timings of when the
        atoms are imaged & when they receive LMT kicks. Store this for later use

        t=0 should be when the atoms are dropped from the dipole trap, (x,y) =
        (0,0) is the location of the atom cloud trap at t=0.

        This method is intended to be called by the experiment code. Finding out
        these facts is out-of-scope for this module.

        Must be called at least once before the first image is taken.
        """
        # FIXME do stuff here

    @kernel
    def get_rois(self) -> List[tuple[int, int, int, int]]:
        half_width = self.roi_width.get() // 2
        half_height = self.roi_height.get() // 2

        gnd_roi = (
            max(0, self.gnd_x - half_width),
            max(0, self.gnd_y - half_height),
            min(self.andor_sensor_width, self.gnd_x + half_width),
            min(
                2 * self.andor_sensor_height, self.gnd_y + half_height
            ),  # Double the sensor's height because of the Frame Transfer buffer
        )
        excited_roi = (
            max(0, self.excited_x - half_width),
            max(0, self.excited_y - half_height),
            min(self.andor_sensor_width, self.excited_x + half_width),
            min(2 * self.andor_sensor_height, self.excited_y + half_height),
        )

        return [gnd_roi, excited_roi]  # type: ignore


class NormalisedFastKineticsLMTCorrected(NormalisedFastKineticsClockPulseMixin):
    def get_andor_camera_config_hook(self) -> AndorCameraConfig:
        pass  # FIXME stuff
