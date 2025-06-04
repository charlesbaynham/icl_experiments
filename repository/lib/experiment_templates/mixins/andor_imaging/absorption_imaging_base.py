import logging
from typing import List

import numpy as np
from artiq.language import host_only
from artiq.language import kernel
from artiq.language import parallel
from artiq.language.core import delay
from ndscan.experiment import FloatChannel
from ndscan.experiment import OpaqueChannel
from ndscan.experiment.parameters import FloatParam
from ndscan.experiment.parameters import FloatParamHandle
from ndscan.experiment.parameters import IntParam

from repository.lib import constants
from repository.lib.experiment_templates.mixins.andor_imaging.imaging_base import (
    AndorImagingBase,
)
from repository.lib.experiment_templates.mixins.andor_imaging.imaging_base import (
    fit_2d_gaussian,
)
from repository.lib.fragments.cameras.andor_camera import AndorCameraControl

logger = logging.getLogger(__name__)

DATASET_OD_KEY = "abs_od_img"


class AbsorptionImagingBase(AndorImagingBase):
    """
    Image three times: once with light and atoms, once with light and no atoms, and once with neither.
    Then calculate the atom number and return an optical density image.

    This is a mixin - see the documentation for :mod:`~.red_mot_experiment` for
    details.

    Kernel hooks used (multiple mixins cannot use the same hooks):

    * :meth:`~do_imaging_hook_andor`
    * :meth:`~save_andor_data_hook`
    * :meth:`~post_sequence_cleanup_hook`
    * :meth:`~save_andor_data_hook`
    """

    num_andor_images = 3
    num_absorption_rois = 1
    num_images_per_series = 3
    num_grabber_readouts = 3

    def build_fragment(self):
        super().build_fragment()

        self.setattr_param(
            "set_topica_pre_delay",
            FloatParam,
            "Toptica setting pre-delay",
            default=0.0,
            unit="ms",
        )
        self.set_topica_pre_delay: FloatParamHandle

        self.setattr_param(
            "delay_between_absorption_pulses",
            FloatParam,
            "Delay after absorption pulse before second",
            default=30e-3,
            unit="ms",
        )
        self.delay_between_absorption_pulses: FloatParamHandle

        self.setattr_param(
            "delay_before_bg_pulse",
            FloatParam,
            description="Delay before background pulse",
            min=0,
            unit="ms",
            default=constants.ANDOR_CAMERA_BACKGROUND_DELAY,
        )
        self.delay_before_bg_pulse: FloatParamHandle

        default_abs_rois = self.get_default_abs_rois()

        for i, (x0, y0, x1, y1) in enumerate(default_abs_rois):
            self.setattr_param(
                f"abs_roi_{i}_x0",
                IntParam,
                f"Abs ROI {i} x0",
                default=x0,
                min=0,
                max=512,
            )
            self.setattr_param(
                f"abs_roi_{i}_x1",
                IntParam,
                f"Abs ROI {i} x1",
                default=x1,
                min=0,
                max=512,
            )
            self.setattr_param(
                f"abs_roi_{i}_y0",
                IntParam,
                f"Abs ROI {i} y0",
                default=y0,
                min=0,
                max=512,
            )
            self.setattr_param(
                f"abs_roi_{i}_y1",
                IntParam,
                f"Abs ROI {i} y1",
                default=y1,
                min=0,
                max=512,
            )

        # force use of andor driver to ensure em gain can be set to 0
        self.override_param("use_andor_driver", True)
        self.setattr_param_rebind("pre_trigger_delay", self.andor_camera_control)
        self.override_param("pre_trigger_delay", 50e-6)
        # self.setattr_param_rebind("delivery_settling_duration", self.fluorescence_pulse)
        # self.override_param("delivery_settling_duration", 6e3)

    def host_setup(self):
        super().host_setup()
        self.andor_camera_control.cam.stop_acquisition()
        em_gain = self.andor_camera_control.cam.get_EMCCD_gain()[0]
        self.andor_camera_control.cam.set_EMCCD_gain(0)
        if em_gain != 0:
            raise ValueError(
                "EM gain should be 0 for absorption imaging. Setting to 0."
            )
        self.andor_camera_control.cam.start_acquisition()  # HACK base and andor cam frag should be changed so acq is only started once.

        self.ccb.issue(
            "create_applet",
            "Optical Density Image",
            f"${{python}} -m custom_artiq_applets.full_img_applet {DATASET_OD_KEY} --default_rois '{self.get_abs_rois()}' --dataset_prefix od_omage",
        )

        andor_exposure = 2 * self.fluorescence_pulse.fluorescence_pulse_duration.get()

        logger.warning(
            "Please ensure that the Andor is in Kinetics mode (not Fast Kinetics) with NO EM GAIN!"
            " And that exposure is set to at least %f us",
            1e6 * andor_exposure,
        )

    def hook_setup_andor(self):
        self.setattr_fragment("andor_camera_control", AndorCameraControl)
        self.andor_camera_control: AndorCameraControl

        self.hook_setup_andor_results()

    def hook_setup_andor_results(self):
        # self.setattr_result("atoms_img", OpaqueChannel)
        # self.atoms_img: OpaqueChannel
        # self.setattr_result("light_img", OpaqueChannel)
        # self.light_img: OpaqueChannel
        # self.setattr_result("bg_img", OpaqueChannel)
        # self.bg_img: OpaqueChannel
        self.setattr_result("od_img", OpaqueChannel)
        self.od_img: OpaqueChannel
        self.setup_gauss_fit_results()

        self.atom_numbers: List[FloatChannel] = []
        for i in range(self.num_absorption_rois):
            atom_number = self.setattr_result(f"atom_number_{i}", FloatChannel)
            self.atom_numbers.append(atom_number)

    @kernel
    def start_of_red_broadband_hook(self):
        # The Andor camera shutter needs ~120ms to open, so start this at the
        # beginning of the red stages. If the total red mot sequence takes less
        # time than this then we'll have problems
        self.andor_camera_control.set_shutter(True)

    @kernel
    def do_imaging_hook_andor(self):
        """
        Hook for the imaging sequence. This hook runs after the spectroscopy
        etc. is completed, and should handle imaging with the Andor camera.
        """
        # step blue frequency
        if self.imagingsetup.set_toptica_analog.freq_step.get() != 0.0:
            delay(-self.set_topica_pre_delay.get())
            self.imagingsetup.set_toptica_analog.step_freq()
            delay(self.set_topica_pre_delay.get())

        # Image with atoms
        self.do_pulse()

        # Reset blue frequency
        if self.imagingsetup.set_toptica_analog.freq_step.get() != 0.0:
            self.imagingsetup.set_toptica_analog.reset_freq()

        # Wait for atoms to disappear
        delay(self.delay_between_absorption_pulses.get())

        # Image without atoms
        self.do_pulse()

        # Trigger the third time without any light
        delay(self.delay_before_bg_pulse.get())
        self.do_pulse(with_light=False)

    @kernel
    def do_pulse(self, with_light=True):
        """
        We want the exposure time to be twice the pulse duration
        """
        exposure = 2 * self.fluorescence_pulse.fluorescence_pulse_duration.get()
        with parallel:
            self.andor_camera_control.trigger(
                exposure=exposure,
                control_shutter=False,
            )
            if with_light:
                self.fluorescence_pulse.do_imaging_pulse(ignore_final_shutters=True)

    @host_only
    def process_andor_image_hook(self, images):
        atoms_img = images[0]
        light_img = images[1]
        bg_img = images[2]

        Ns, od_slices, od_img, n_invalid = self.calc_atom_number(
            atoms_img, light_img, bg_img
        )
        self.set_dataset(
            DATASET_OD_KEY, od_img, broadcast=True, persist=False, archive=False
        )

        for i in range(self.num_absorption_rois):
            self.atom_numbers[i].push(Ns[i])
            self.set_dataset(
                DATASET_OD_KEY + f"slice_{i}",
                od_slices[i],
                broadcast=True,
                persist=False,
                archive=False,
            )

        image_size = np.prod(np.shape(od_img))
        if n_invalid > image_size / 1000:
            logger.warning(f"{n_invalid} invalid pixels. Too many!")
        else:
            logger.info(f"{n_invalid} invalid pixels. Probably fine.")

        if self.andor_camera_control.save_raw_andor_image.get():
            # self.atoms_img.push(atoms_img)
            # self.light_img.push(light_img)
            # self.bg_img.push(bg_img)
            self.od_img.push(od_img)
        else:
            # self.atoms_img.push([])
            # self.light_img.push([])
            # self.bg_img.push([])
            self.od_img.push([])

        if self.do_gauss_fit.get():
            logger.debug("Doing gauss fitod_im")
            self.do_gauss_fit_hook([od_img])
        else:
            logger.debug("Not doing gauss fit")
            for i in range(len(self.amps)):
                self.push_gauss_fit_pars([np.nan] * 5, i)

    @host_only
    def do_gauss_fit_hook(self, imgs_array):
        for img_array in imgs_array:
            self.fit_from_abs_rois(img_array)

    @host_only
    def fit_from_abs_rois(self, image):
        for i in range(self.num_absorption_rois):
            sliced_image, offsets = self.andor_camera_control.slice_from_roi_params(
                image, i, prefix="abs_roi_", obj=self
            )
            popt = fit_2d_gaussian(sliced_image, offsets)
            self.push_gauss_fit_pars(popt, i)

    def setup_gauss_fit_results(self):
        self.amps: List[FloatChannel] = []
        self.x_pos: List[FloatChannel] = []
        self.y_pos: List[FloatChannel] = []
        self.sigmas_x: List[FloatChannel] = []
        self.sigmas_y: List[FloatChannel] = []
        # print(f"num_gauss_fit_results: {num_gauss_fit_results}")
        for i in range(self.num_absorption_rois):
            self.amps.append(
                self.setattr_result(
                    f"amp_{i}", FloatChannel, display_hints={"priority": -1}
                )
            )
            self.x_pos.append(
                self.setattr_result(
                    f"x_pos_{i}", FloatChannel, display_hints={"priority": -1}
                )
            )
            self.y_pos.append(
                self.setattr_result(
                    f"y_pos_{i}", FloatChannel, display_hints={"priority": -1}
                )
            )
            self.sigmas_x.append(
                self.setattr_result(
                    f"sigma_x_{i}", FloatChannel, display_hints={"priority": -1}
                )
            )
            self.sigmas_y.append(
                self.setattr_result(
                    f"sigma_y_{i}", FloatChannel, display_hints={"priority": -1}
                )
            )

    @host_only
    def calc_atom_number(
        self, atoms_img: np.ndarray, light_img: np.ndarray, bg_img: np.ndarray
    ):
        # TODO: should this go in an analysis script collection?
        """
        Subtract background and take quotient of images with and without atoms
        Scale by pixel size and absorption cross-section to get atom number.
        Uses numpy MaskedArrays to deal with invalid pixels

        Returns: Atom number, optical density image, number of invalid pixels
        """

        A_pixel = constants.ANDOR_CAMERA_FACTS["A_pixel"]
        lam = constants.SR_FACTS["WAVELENGTHS"]["461_88"]
        sigma_0 = 3 * lam**2 / (2 * np.pi)

        atoms_img = atoms_img.astype(float)
        light_img = light_img.astype(float)
        bg_img = bg_img.astype(float)
        atoms_no_bg = atoms_img - bg_img
        light_no_bg = light_img - bg_img

        light_no_bg_ma = np.ma.masked_where(
            light_no_bg == 0, light_no_bg
        )  # avoid divide by zero
        quotient = atoms_no_bg / light_no_bg_ma
        quotient = np.ma.filled(
            quotient, 1
        )  # fill with 1s - no contribution to atom number
        quotient_ma = np.ma.masked_less_equal(quotient, 0.0)  # avoid invalid log error
        n_invalid = np.sum(quotient_ma.mask)  # get number of invalid pixels
        quotient_fixed = np.ma.filled(
            quotient_ma, 1
        )  # fill with 1s - no contribution to atom number

        OD = -np.log(quotient_fixed)

        Ns = []
        OD_slices = []

        for i, roi in enumerate(self.get_abs_rois()):
            x0 = roi[0]
            y0 = roi[1]
            x1 = roi[2]
            y1 = roi[3]
            OD_slice = OD[x0:x1, -y1:-y0]

            N = np.sum(OD_slice) * A_pixel / sigma_0

            Ns.append(N)
            OD_slices.append(OD_slice)
            logger.debug(f"OD slice {i}: {OD_slice}")

        return Ns, OD_slices, OD, n_invalid

    @host_only
    def get_abs_rois(self):
        """
        Get the absorption ROIs from the parameters
        """
        abs_rois = []
        for i in range(self.num_absorption_rois):
            param_prefix = f"abs_roi_{i}_"
            x0 = getattr(self, param_prefix + "x0").get()
            y0 = getattr(self, param_prefix + "y0").get()
            x1 = getattr(self, param_prefix + "x1").get()
            y1 = getattr(self, param_prefix + "y1").get()
            abs_rois.append([x0, y0, x1, y1])
        return abs_rois

    @kernel
    def save_andor_data_hook(self):
        """
        Consume all slack and save the photos
        """
        self._call_camera_rpc()

    @host_only
    def get_default_abs_rois(self):
        return [[0, 0, 512, 512]]
