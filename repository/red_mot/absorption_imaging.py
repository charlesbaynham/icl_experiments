import logging

import numpy as np
from artiq.experiment import delay
from artiq.experiment import kernel
from artiq.experiment import rpc
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

        self.setattr_result("andor_sum_0", FloatChannel)
        self.setattr_result("andor_sum_1", FloatChannel)
        self.setattr_result("andor_sum_2", FloatChannel)
        # self.setattr_result("andor_sum_3", FloatChannel)

        self.setattr_result("absorption", FloatChannel)

        self.andor_sum_0: FloatChannel
        self.andor_sum_1: FloatChannel
        self.andor_sum_2: FloatChannel
        self.andor_sum_3: FloatChannel

        self.absorption: FloatChannel

        self.setattr_result("andor_abs_img", OpaqueChannel)
        self.andor_abs_img: OpaqueChannel

    def host_setup(self):
        super().host_setup()

        self.ccb.issue(
            "create_applet",
            f"atoms_img",
            f"${{artiq_applet}}image atoms_img",
        )

        self.ccb.issue(
            "create_applet",
            f"light_img",
            f"${{artiq_applet}}image light_img",
        )
        self.ccb.issue(
            "create_applet",
            f"bg_img",
            f"${{artiq_applet}}image bg_img",
        )
        self.ccb.issue(
            "create_applet",
            f"andor_abs_img",
            f"${{artiq_applet}}image andor_abs_img_dataset",
        )

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

    @rpc(flags={"async"})
    def _call_camera_rpc(self):
        # imgs = self.andor_camera_control.readout_n_images(n_frames=3, timeout=1)
        # atoms_img = imgs[0]
        # light_img = imgs[1]
        # bg_img = imgs[2]

        atoms_img = self.andor_camera_control.readout_image(timeout=1)
        light_img = self.andor_camera_control.readout_image(timeout=1)
        bg_img = self.andor_camera_control.readout_image(timeout=1)

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

        self.set_dataset(
            "atoms_img",
            np.int32(atoms_img),
            broadcast=True,
            persist=False,
            archive=False,
        )
        self.set_dataset(
            "light_img",
            light_img,
            broadcast=True,
            persist=False,
            archive=False,
        )
        self.set_dataset(
            "bg_img",
            bg_img,
            broadcast=True,
            persist=False,
            archive=False,
        )

        self.set_dataset(
            "andor_abs_img_dataset",
            img_abs,
            broadcast=True,
            persist=False,
            archive=False,
        )
        # TODO rebind this instead
        if self.andor_camera_control.save_raw_andor_image.get():
            self.andor_abs_img.push(img_abs)
        else:
            self.andor_abs_img.push([])

    @kernel
    def save_andor_data_hook(self):
        """
        Hook to save data from the Andor camera

        We took four images, each separately as normal (i.e. not fast kinetics)
        images.
        """

        n = 3
        sums = [0] * n

        timeout_mu = self.core.get_rtio_counter_mu() + self.core.seconds_to_mu(1.0)

        for i in range(n):
            s = [0]
            m = [0.0]
            self.andor_camera_control.readout_ROIs(s, m, timeout_mu)
            sums[i] = s[0]

        self.andor_sum_0.push(sums[0])
        self.andor_sum_1.push(sums[1])
        self.andor_sum_2.push(sums[2])
        # self.andor_sum_3.push(sums[3])

        self.absorption.push(sums[1] - sums[0])

        if self.use_andor_driver.get():
            self._call_camera_rpc()


AbsorptionRedMOT = make_fragment_scan_exp(AbsorptionRedMOTFrag)
