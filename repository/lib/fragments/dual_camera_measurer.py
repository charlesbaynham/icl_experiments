import logging

import numpy as np
from artiq.coredevice.core import Core
from artiq.experiment import host_only
from artiq.experiment import kernel
from artiq.experiment import rpc
from ndscan.experiment import Fragment
from ndscan.experiment import ResultChannel
from ndscan.experiment.parameters import FloatParam
from ndscan.experiment.parameters import FloatParamHandle
from ndscan.experiment.result_channels import FloatChannel
from ndscan.experiment.result_channels import IntChannel
from ndscan.experiment.result_channels import OpaqueChannel

from repository.lib.fragments.flir_camera import Chamber2HorizontalCamera
from repository.lib.fragments.flir_camera import Chamber2VerticalCamera


logger = logging.getLogger(__name__)


DATASET_KEY_H = "latest_bg_corrected_image_horiz"
DATASET_KEY_V = "latest_bg_corrected_image_vert"


class BGCorrectedMeasurement(Fragment):
    """
    Background-corrected image aquisition with the FLIR cameras
    """

    def build_fragment(self):
        self.setattr_device("core")
        self.core: Core

        self.setattr_device("ccb")

        # %% Parameters

        self.setattr_param(
            "exposure_horiz",
            FloatParam,
            description="Image exposure horizontal",
            default=1e-3,
            min=0,
            unit="us",
            step=1,
        )
        self.exposure_horiz: FloatParamHandle

        self.setattr_param(
            "exposure_vert",
            FloatParam,
            description="Image exposure vertical",
            default=1e-3,
            min=0,
            unit="us",
            step=1,
        )
        self.exposure_vert: FloatParamHandle

        # %% Fragments

        self.setattr_fragment(
            "mot_measurer_camera_horizontal", Chamber2HorizontalCamera
        )
        self.mot_measurer_camera_horizontal: Chamber2HorizontalCamera

        self.setattr_fragment("mot_measurer_camera_vertical", Chamber2VerticalCamera)
        self.mot_measurer_camera_vertical: Chamber2VerticalCamera

        # %%  Results

        self.setattr_result("image_horizontal", OpaqueChannel)
        self.image_horizontal: ResultChannel

        self.setattr_result(
            "image_horizontal_timestamp", IntChannel, display_hints={"priority": -1}
        )
        self.image_horizontal_timestamp: ResultChannel

        self.setattr_result("image_horizontal_mean", FloatChannel)
        self.image_horizontal_mean: ResultChannel

        self.setattr_result("image_vertical", OpaqueChannel)
        self.image_vertical: ResultChannel

        self.setattr_result(
            "image_vertical_timestamp", IntChannel, display_hints={"priority": -1}
        )
        self.image_vertical_timestamp: ResultChannel

        self.setattr_result("image_vertical_mean", FloatChannel)
        self.image_vertical_mean: ResultChannel

        # %% Kernel attributes
        self.image_index = 0
        self.bg_index = -1
        self.signal_index = -1

        self.debug_enabled = logger.isEnabledFor(logging.DEBUG)

    def host_setup(self) -> None:
        super().host_setup()

        # Prepare cameras to be triggered for 2x acquisitions
        self.mot_measurer_camera_horizontal.ready_for_trigger(
            self.exposure_horiz.get() * 1e6, num_images=2
        )
        self.mot_measurer_camera_vertical.ready_for_trigger(
            self.exposure_vert.get() * 1e6, num_images=2
        )

        # Launch bg-corrected monitors
        self.set_dataset(
            DATASET_KEY_H,
            np.array([[0.0]]),
            broadcast=True,
            persist=False,
            archive=False,
        )
        self.set_dataset(
            DATASET_KEY_V,
            np.array([[0.0]]),
            broadcast=True,
            persist=False,
            archive=False,
        )

        self.ccb.issue(
            "create_applet",
            "BG-corrected horizontal image",
            f"${{artiq_applet}}image {DATASET_KEY_H}",
        )
        self.ccb.issue(
            "create_applet",
            "BG-corrected vertical image",
            f"${{artiq_applet}}image {DATASET_KEY_V}",
        )

    @kernel
    def trigger_signal(self):
        """
        Trigger signal pictures to be taken now on each camera

        Pictures are stored in the camera's internal buffer any must be read out
        using :meth:`.save_data` otherwise they will be lost.

        Occurs at the time of calling via an RPC, not at the timeline.
        """
        if self.image_index > 1:
            # We've already taken two images - fail!
            raise RuntimeError("Two images already taken without being read out")
        if self.signal_index != -1:
            raise RuntimeError("Signal image already taken without being read out")

        if self.debug_enabled:
            logger.info(
                "Taking signal image with image_index = %d, signal_index = %d, bg_index = %d",
                self.image_index,
                self.signal_index,
                self.bg_index,
            )

        self._trigger_rpc()

        self.signal_index = self.image_index
        self.image_index += 1

    @kernel
    def trigger_background(self):
        """
        Trigger background pictures to be taken now on each camera

        Pictures are stored in the camera's internal buffer any must be read out
        using :meth:`.save_data` otherwise they will be lost.

        Occurs at the time of calling via an RPC, not at the timeline.
        """
        if self.image_index > 1:
            # We've already taken two images - fail!
            raise RuntimeError("Two images already taken without being read out")
        if self.bg_index != -1:
            raise RuntimeError("Background image already taken without being read out")

        if self.debug_enabled:
            logger.info(
                "Taking background image with image_index = %d, signal_index = %d, bg_index = %d",
                self.image_index,
                self.signal_index,
                self.bg_index,
            )

        self._trigger_rpc()

        self.bg_index = self.image_index
        self.image_index += 1

    @rpc(flags={"async"})
    def _trigger_rpc(self):
        self.mot_measurer_camera_horizontal.trigger()
        self.mot_measurer_camera_vertical.trigger()

    @kernel
    def save_data(
        self,
    ):
        """
        Retrieve images from the cameras and save them to ndscan ResultChannels
        """
        if self.debug_enabled:
            logger.info(
                "Calling save_data with image_index = %d, signal_index = %d, bg_index = %d",
                self.image_index,
                self.signal_index,
                self.bg_index,
            )

        self._save_data_rpc(self.bg_index, self.signal_index)

        self.bg_index = -1
        self.signal_index = -1
        self.image_index = 0

    @rpc
    def _save_data_rpc(self, bg_index, signal_index):
        """
        Retrieve images from the cameras and save them to ndscan ResultChannels
        """

        if bg_index == -1:
            raise RuntimeError("No BG image was taken")
        if signal_index == -1:
            raise RuntimeError("No signal image was taken")

        timestamps_horiz, images_horiz = zip(
            *self.mot_measurer_camera_horizontal.get_frames(
                timeout=1 + self.exposure_horiz.get()
            )
        )
        timestamps_vert, images_vert = zip(
            *self.mot_measurer_camera_vertical.get_frames(
                timeout=1 + self.exposure_vert.get()
            )
        )

        timestamp_horiz = timestamps_horiz[signal_index]
        timestamp_vert = timestamps_vert[signal_index]

        # Here, we convert the uint8 images to int16 so that we can support negative numbers
        image_horiz = images_horiz[signal_index].astype("int16") - images_horiz[
            bg_index
        ].astype("int16")
        image_vert = images_vert[signal_index].astype("int16") - images_vert[
            bg_index
        ].astype("int16")

        image_horiz_mean = np.mean(np.array(image_horiz).flat)
        image_vert_mean = np.mean(np.array(image_vert).flat)

        logger.debug("image_horiz.shape = %s", image_horiz.shape)
        logger.debug("image_vert.shape = %s", image_vert.shape)

        self.image_horizontal_timestamp.push(timestamp_horiz)
        self.image_vertical_timestamp.push(timestamp_vert)

        self.image_horizontal_mean.push(image_horiz_mean)
        self.image_vertical_mean.push(image_vert_mean)

        self.image_horizontal.push(image_horiz)
        self.image_vertical.push(image_vert)

        self._update_monitor(image_horiz, image_vert)

    @host_only
    def _update_monitor(self, img_h, img_v):
        # convert to int instead of uint8 for plotting
        self.set_dataset(
            DATASET_KEY_H,
            np.array(img_h).astype("int"),
            broadcast=True,
            persist=False,
            archive=False,
        )
        self.set_dataset(
            DATASET_KEY_V,
            np.array(img_v).astype("int"),
            broadcast=True,
            persist=False,
            archive=False,
        )
