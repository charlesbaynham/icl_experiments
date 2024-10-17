import logging

import numpy as np
from artiq.experiment import delay
from artiq.experiment import kernel
from artiq.experiment import rpc
from ndscan.experiment import FloatChannel
from ndscan.experiment import OpaqueChannel
from ndscan.experiment.entry_point import make_fragment_scan_exp
from ndscan.experiment.parameters import BoolParamHandle
from ndscan.experiment.parameters import FloatParam
from ndscan.experiment.parameters import FloatParamHandle

from repository.lib.experiment_templates.red_mot_experiment import RedMOTWithExperiment
from repository.lib.fragments.cameras.andor_camera import AndorCameraControl

logger = logging.getLogger(__name__)


class AbsorptionRedMOT(RedMOTWithExperiment):
    """
    Image red MOT with absorption
    """

    @kernel
    def do_experiment_after_red_mot_hook(self):
        pass

    def build_fragment(self):
        self.setattr_device("ccb")

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
        andor_exposure = 2 * self.fluorescence_pulse.fluorescence_pulse_duration.get()
        logger.warning(
            "Please ensure that the Andor is in Kinetics mode (not Fast Kinetics) with NO EM GAIN!"
            " And that exposure is set to at least %f us",
            1e6 * andor_exposure,
        )

        return super().host_setup()

    @kernel
    def start_of_red_broadband_hook(self):
        # The Andor camera shutter needs ~120ms to open, so start this at the
        # beginning of the red stages. If the total red mot sequence takes less
        # time than this then we'll have problems
        self.andor_camera_control.set_shutter(True)

    # @kernel
    # def do_pulse(self, andor_exposure):
    #     """ """
    #     with parallel:
    #         self.andor_camera_control.trigger(
    #             exposure=andor_exposure,
    #             control_shutter=False,
    #         )
    #         # self.fluorescence_pulse.do_imaging_pulse(ignore_final_shutters=True)
    #         # logger.info("this is where I would do an imaging pulse")

    @kernel
    def do_imaging_hook(self):
        """
        Hook for the imaging sequence. This hook runs after the spectroscopy
        etc. is completed, and should handle imaging with the Andor camera.
        """
        andor_exposure = 2 * self.fluorescence_pulse.fluorescence_pulse_duration.get()

        # Image with atoms
        self.do_pulse(andor_exposure)

        # Wait for atoms to disappear
        delay(self.delay_between_absorption_pulses.get())

        # Image without atoms
        self.do_pulse(andor_exposure)

        # Trigger the third time without any light
        delay(self.delay_before_background_pulse.get())
        self._do_pulse_no_light(andor_exposure)

        # # Trigger again since we're still in fast kinetics mode so we must take two images
        # delay(self.delay_between_absorption_pulses.get())
        # self._do_pulse_no_light(andor_exposure)

    @kernel
    def _do_pulse_no_light(self, andor_exposure):
        delay(-0.5 * andor_exposure)
        self.andor_camera_control.trigger(
            exposure=andor_exposure,
            control_shutter=False,
        )
        delay(0.5 * andor_exposure)

    def hook_setup_andor(self):
        """
        Setup the Andor camera with default settings
        """
        self.setattr_fragment("andor_camera_control", AndorCameraControl)
        self.andor_camera_control: AndorCameraControl

        self.setattr_param_rebind("use_andor_driver", self.andor_camera_control)
        self.use_andor_driver: BoolParamHandle

    # def hook_setup_andor(self):
    #     """
    #     Setup the Andor camera to use 4x ROIs since we're expecting fast
    #     kinetics mode with 2x images which we'll repeat.

    #     Each image is the full sensor size, so we'll use the normal ROI

    #     TODO: Set up Fast Kinetics mode here too
    #     """

    #     self.setattr_fragment(
    #         "andor_camera_control",
    #         AndorCameraControl,
    #         roi_defaults=[
    #             [
    #                 constants.ANDOR_ROI_X0,
    #                 i * constants.ANDOR_SENSOR_HEIGHT + constants.ANDOR_ROI_Y0,
    #                 constants.ANDOR_ROI_X1,
    #                 i * constants.ANDOR_SENSOR_HEIGHT + constants.ANDOR_ROI_Y1,
    #             ]
    #             for i in range(2)
    #         ],
    #     )
    #     self.andor_camera_control: AndorCameraControl

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
        light_no_bg = light_img - bg_img
        quotient = np.zeros_like(atoms_no_bg)
        np.divide(atoms_no_bg, light_no_bg, out=quotient, where=light_no_bg != 0)
        img_abs = -np.log(quotient)

        pixel_size = 16e-6
        lam = 460.86177e9
        pi = np.pi
        sigma = 3 * lam**2 / (2 * pi)

        N = np.sum(np.sum(img_abs)) * pixel_size**2 / sigma

        self.absorption.push(N)

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

        We took four images, each seperately as normal (i.e. not fast kinetics)
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

        if self.use_andor_driver.get():
            self._call_camera_rpc()


AbsorptionRedMOTExp = make_fragment_scan_exp(AbsorptionRedMOT)
