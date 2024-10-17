import logging

import numpy as np
from artiq.experiment import delay, host_only
from artiq.experiment import kernel
from artiq.experiment import now_mu
from artiq.experiment import rpc
from ndscan.experiment import FloatChannel
from ndscan.experiment import OpaqueChannel
from ndscan.experiment.parameters import FloatParam
from ndscan.experiment.parameters import FloatParamHandle

from repository.lib import constants

from .imaging_base import AndorImagingBase, ANDOR_MONITOR_DATASET

logger = logging.getLogger(__name__)


class BGCorrectedAndorImage(AndorImagingBase):
    """
    Image with a single fluorescence pulse using the Andor camera then take another for background subtraction

    This is a mixin - see the documentation for :mod:`~.red_mot_experiment` for
    details.

    Kernel hooks used (multiple mixins cannot use the same hooks):

    * :meth:`~do_imaging_hook_andor`
    * :meth:`~save_andor_data_hook`
    """

    num_andor_images = 2

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
        # Use default imaging setup
        super().hook_setup_andor()

        self.setattr_param(
            "delay_before_bg_pulse",
            FloatParam,
            description="Delay before background pulse",
            min=0,
            unit="ms",
            default=constants.ANDOR_CAMERA_BACKGROUND_DELAY,
        )
        self.delay_before_bg_pulse: FloatParamHandle

        # FIXME: This should be removed or made generic
        self.setattr_result("andor_sum", FloatChannel, display_hints={"priority": -1})
        self.setattr_result("andor_mean", FloatChannel, display_hints={"priority": -1})
        self.setattr_result("andor_mean_bg_corrected", FloatChannel)
        self.andor_mean_bg_corrected: FloatChannel
        self.andor_sum: FloatChannel
        self.andor_mean: FloatChannel

    @kernel
    def do_imaging_hook_andor(self):
        """
        Hook for the imaging sequence. This hook runs after the spectroscopy
        etc. is completed, and should handle imaging with the Andor camera.
        """
        # Image atoms
        self.do_pulse()

        # Drop them
        self.blue_3d_mot.chamber_2_field_setter.set_mot_gradient(0.0)

        delay(self.delay_before_bg_pulse.get())

        # Image background with no atoms
        self.do_pulse()

    @host_only
    def update_andor_monitor_hook(self):
        """
        Update the andor monitor with an appropriate image

        Override this hook to select a different image. AndorImagingBase will
        create `num_andor_images`  ResultChannels containing the Andor images,
        so you can use these. NDScan supports a `get_last` method on
        ResultChannels sinks so you can use this: see the example below which
        shows the first image by default.
        """
        try:
            img_array = self.andor_images[0].sink.get_last()
            bg_img_array = self.andor_images[1].sink.get_last()
            corrected_img_array = np.int32(img_array) - np.int32(bg_img_array)
        except AttributeError:
            corrected_img_array = [[0.0]]

        if img_array is None:
            corrected_img_array = [[0.0]]

        self.set_dataset(
            ANDOR_MONITOR_DATASET,
            corrected_img_array,
            broadcast=True,
            persist=False,
            archive=False,
        )

    @kernel
    def save_andor_data_hook(self):
        "Consume all slack and save the photos"
        # FIXME: genericise this
        self.core.wait_until_mu(now_mu())

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
