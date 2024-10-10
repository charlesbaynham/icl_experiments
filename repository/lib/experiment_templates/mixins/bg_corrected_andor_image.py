import logging

import numpy as np
from artiq.experiment import delay
from artiq.experiment import kernel
from artiq.experiment import now_mu
from artiq.experiment import rpc
from ndscan.experiment import FloatChannel
from ndscan.experiment import OpaqueChannel
from ndscan.experiment.parameters import BoolParamHandle
from ndscan.experiment.parameters import FloatParam
from ndscan.experiment.parameters import FloatParamHandle

from repository.lib import constants
from repository.lib.experiment_templates.red_mot_experiment import RedMOTWithExperiment
from repository.lib.fragments.cameras.andor_camera import AndorCameraControl

logger = logging.getLogger(__name__)


class BGCorrectedAndorImage(RedMOTWithExperiment):
    """
    Image with a single fluorescence pulse using the Andor camera then take another for background subtraction

    This is a mixin - see the documentation for :mod:`~.red_mot_experiment` for
    details.

    Kernel hooks used (multiple mixins cannot use the same hooks):

    * :meth:`~do_imaging_hook`
    * :meth:`~save_data_hook`
    """

    def build_fragment(self):
        super().build_fragment()

        self.setattr_device("ccb")

        self.setattr_param(
            "delay_before_bg_pulse",
            FloatParam,
            description="Delay before background pulse",
            min=0,
            unit="ms",
            default=constants.ANDOR_CAMERA_BACKGROUND_DELAY,
        )
        self.delay_before_bg_pulse: FloatParamHandle

    def host_setup(self):
        self.ccb.issue(
            "create_applet",
            "Bg subtracted Andor image",
            f"${{artiq_applet}}image {'corrected_img'}",
        )
        self.ccb.issue(
            "create_applet",
            "Andor image w/ atoms",
            f"${{artiq_applet}}image {'atom_img_array'}",
        )

        self.ccb.issue(
            "create_applet",
            "Bg Andor image",
            f"${{artiq_applet}}image {'bg_img_array'}",
        )

        return super().host_setup()

    def hook_setup_andor(self):
        self.setattr_fragment("andor_camera_control", AndorCameraControl)
        self.andor_camera_control: AndorCameraControl

        self.setattr_result("andor_sum", FloatChannel, display_hints={"priority": -1})
        self.setattr_result("andor_mean", FloatChannel, display_hints={"priority": -1})
        self.setattr_result("andor_mean_bg_corrected", FloatChannel)
        self.andor_mean_bg_corrected: FloatChannel
        self.andor_sum: FloatChannel
        self.andor_mean: FloatChannel

        self.setattr_result("andor_sum_slice_x", OpaqueChannel)
        self.setattr_result("andor_sum_slice_y", OpaqueChannel)
        self.setattr_result("andor_bg_corrected", OpaqueChannel)
        self.andor_sum_slice_x: OpaqueChannel
        self.andor_sum_slice_y: OpaqueChannel
        self.andor_bg_corrected: OpaqueChannel

        self.setattr_param_rebind("use_andor_driver", self.andor_camera_control)
        self.use_andor_driver: BoolParamHandle

    @kernel
    def start_of_red_broadband_hook(self):
        # The Andor camera shutter needs ~120ms to open, so start this at the
        # beginning of the red stages. If the total red mot sequence takes less
        # time than this then we'll have problems
        self.andor_camera_control.set_shutter(True)

    @kernel
    def do_imaging_hook(self):
        self.do_imaging_hook_andor()

    @kernel
    def do_imaging_hook_andor(self):
        """
        Hook for the imaging sequence. This hook runs after the spectroscopy
        etc. is completed, and should handle imaging with the Andor camera.
        """
        andor_exposure = 2 * self.fluorescence_pulse.fluorescence_pulse_duration.get()

        # Image atoms
        self.do_pulse(andor_exposure)

        # Drop them
        self.blue_3d_mot.chamber_2_field_setter.set_mot_gradient(0.0)

        delay(self.delay_before_bg_pulse.get())

        # Image background with no atoms
        self.do_pulse(andor_exposure)

    @rpc(flags={"async"})
    def _call_camera_rpc(self):
        # do stuff including writing to resultchannel
        img_array = self.andor_camera_control.readout_image(timeout=1)
        bg_img_array = self.andor_camera_control.readout_image(timeout=1)

        corrected_img_array = np.int32(img_array) - np.int32(bg_img_array)
        sum_slice_x, sum_slice_y = self.andor_camera_control.slice_image(
            corrected_img_array
        )

        self.set_dataset(
            "corrected_img",
            corrected_img_array,
            broadcast=True,
            persist=False,
            archive=False,
        )

        self.set_dataset(
            "atom_img_array",
            img_array,
            broadcast=True,
            persist=False,
            archive=False,
        )

        self.set_dataset(
            "bg_img_array",
            bg_img_array,
            broadcast=True,
            persist=False,
            archive=False,
        )

        self.andor_sum_slice_x.push(sum_slice_x)
        self.andor_sum_slice_y.push(sum_slice_y)

        if self.andor_camera_control.save_raw_andor_image.get():
            self.andor_bg_corrected.push(corrected_img_array)
        else:
            self.andor_bg_corrected.push([])

    @kernel
    def save_data_hook(self):
        "Consume all slack and save the photos"
        self.core.wait_until_mu(now_mu())

        if self.use_andor_driver.get():
            self._call_camera_rpc()

        sum_atoms = [0]
        mean_atoms = [0.0]
        sum_bg = [0]
        mean_bg = [0.0]

        self.andor_camera_control.readout_ROIs(
            sum_atoms,
            mean_atoms,
            timeout_mu=self.core.get_rtio_counter_mu() + self.core.seconds_to_mu(1.0),
        )
        self.andor_camera_control.readout_ROIs(
            sum_bg,
            mean_bg,
            timeout_mu=self.core.get_rtio_counter_mu() + self.core.seconds_to_mu(1.0),
        )

        self.andor_sum.push(sum_atoms[0])
        self.andor_mean.push(mean_atoms[0])
        self.andor_mean_bg_corrected.push(mean_atoms[0] - mean_bg[0])

    @kernel
    def post_sequence_cleanup_hook(self):
        self.post_sequence_cleanup_hook_base()
        self.post_sequence_cleanup_hook_andor()

    @kernel
    def post_sequence_cleanup_hook_andor(self):
        # Ensure shutter is closed, though it should be anyway
        self.core.break_realtime()
        self.andor_camera_control.set_shutter(False)
