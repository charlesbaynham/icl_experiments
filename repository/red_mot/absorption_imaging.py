import logging

import numpy as np
from artiq.experiment import delay
from artiq.experiment import host_only
from artiq.experiment import kernel
from ndscan.experiment import FloatChannel
from ndscan.experiment import OpaqueChannel
from ndscan.experiment.entry_point import make_fragment_scan_exp
from ndscan.experiment.parameters import FloatParam
from ndscan.experiment.parameters import FloatParamHandle

from repository.lib import constants
from repository.lib.experiment_templates.mixins.andor_imaging.imaging_base import (
    AndorImagingBase,
)
from repository.lib.experiment_templates.red_mot_experiment import RedMOTWithExperiment

logger = logging.getLogger(__name__)


class AbsorptionRedMOTFrag(AndorImagingBase, RedMOTWithExperiment):
    """
    Image red MOT with absorption
    """

    num_grabber_rois = 1
    num_grabber_images = 3
    num_andor_images = 3

    @kernel
    def do_experiment_after_red_mot_hook(self):
        pass

    def build_fragment(self):
        super().build_fragment()

        # Set the MOT field to off before the "spectroscopy" (i.e. imaging) starts
        self.override_param("spectroscopy_field_gradient", 0.0)

        # Disable unused params
        for p in ["delay_after_experiment"]:
            self.override_param(p, 0)

        # %% Params

        self.setattr_param(
            "delay_between_absorption_pulses",
            FloatParam,
            "Delay after absorption pulse before second",
            default=30e-3,
            unit="ms",
        )
        self.delay_between_absorption_pulses: FloatParamHandle

        self.setattr_param(
            "delay_before_background_pulse",
            FloatParam,
            "Delay after absoprtion pulse before no-light background image",
            default=50e-3,
            unit="ms",
        )
        self.delay_before_background_pulse: FloatParamHandle

        # %% Results

        self.setattr_result("absorption", FloatChannel)
        self.absorption: FloatChannel

        self.setattr_result("andor_abs_img", OpaqueChannel)
        self.andor_abs_img: OpaqueChannel

    def host_setup(self):
        super().host_setup()

        logger.warning(
            "Please ensure that the Andor is in Kinetics mode (not Fast Kinetics) with NO EM GAIN!"
            " And that exposure is set to at least %f us",
            1e6
            * (
                self.fluorescence_pulse.fluorescence_pulse_duration.get()
                + constants.ANDOR_CAMERA_TRIGGER_ENABLE_TIME
            ),
        )

    @kernel
    def do_imaging_hook(self):
        """
        Hook for the imaging sequence. This hook runs after the spectroscopy
        etc. is completed, and should handle imaging with the Andor camera.
        """
        # Image with atoms
        self.do_pulse()

        # Wait for atoms to disappear
        delay(self.delay_between_absorption_pulses.get())

        # Image without atoms
        self.do_pulse()

        # Trigger the third time without any light
        delay(self.delay_before_background_pulse.get())
        self.do_pulse(with_light=False)

    @host_only
    def get_andor_images(self):
        # Process the absorption image and save it into a ResultChannel
        images = super().get_andor_images()

        if (
            self.use_andor_driver.get()
            and self.andor_camera_control.save_raw_andor_image.get()
        ):
            atoms_img = images[0]
            light_img = images[1]
            bg_img = images[2]

            atoms_no_bg = atoms_img - bg_img
            atoms_no_bg_m = np.ma.masked_less_equal(atoms_no_bg, 0)
            light_no_bg = light_img - bg_img
            light_no_bg_m = np.ma.masked_less_equal(light_no_bg, 0)
            quotient = light_no_bg_m / atoms_no_bg_m
            quotient_m = np.ma.masked_less_equal(quotient, 0)
            img_abs: np.ma.MaskedArray = np.log(quotient_m)
            logger.info(f"number invalid elements: {len(img_abs.mask)}")
            img_abs = np.ma.fix_invalid(img_abs, img_abs.mask, fill_value=0)
            img_abs = img_abs.data

            self.andor_abs_img.push(img_abs)
        else:
            self.andor_abs_img.push([])

        return images

    @kernel
    def process_andor_data_hook(self, sums, means):
        self.absorption.push(sums[1] - sums[0])


AbsorptionRedMOT = make_fragment_scan_exp(AbsorptionRedMOTFrag)
