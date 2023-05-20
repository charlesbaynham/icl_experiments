import logging

import numpy as np
from artiq.coredevice.core import Core
from artiq.experiment import host_only
from artiq.experiment import rpc
from ndscan.experiment import ExpFragment
from ndscan.experiment.entry_point import make_fragment_scan_exp
from ndscan.experiment.parameters import FloatParam
from ndscan.experiment.parameters import FloatParamHandle
from ndscan.experiment.parameters import IntParam
from ndscan.experiment.parameters import IntParamHandle
from ndscan.experiment.result_channels import OpaqueChannel

from repository.lib.other.flir_camera import Chamber2Camera

logger = logging.getLogger(__name__)


class MOTCameraMeasurement(ExpFragment):
    def build_fragment(self):
        self.setattr_device("core")
        self.core: Core

        self.setattr_param(
            "exposure",
            FloatParam,
            description="Exposure per image",
            default=1e-3,
            unit="us",
            step=1,
        )
        self.exposure: FloatParamHandle

        self.setattr_param(
            "image_delay",
            FloatParam,
            description="Delay between startring aquisition of frames",
            default=20e-3,
            min=20e-3,
            unit="ms",
            step=1,
        )
        self.image_delay: FloatParamHandle

        self.setattr_param(
            "number_images",
            IntParam,
            description="Number of images to take",
            default=100,
            min=1,
        )
        self.number_images: IntParamHandle

        self.setattr_result("timestamps", OpaqueChannel)
        self.timestamps: OpaqueChannel

        self.setattr_result("images", OpaqueChannel)
        self.images: OpaqueChannel

    def host_setup(self):
        raise NotImplementedError("I've messed with the camera code and broken this")
        self.camera_driver = Chamber2Camera(
            num_images=self.number_images.get(),
            exposure_us=1e6 * self.exposure.get(),
            delay_ms=1e3 * self.image_delay.get(),
        )
        self._images = None
        return super().host_setup()

    @rpc(flags={"async"})
    def start_camera_measurement(self):
        """
        Start measuring images using pre-defined camera settings

        When finished, images will be available via :meth:`.get_images()`
        """
        self._images = self.camera_driver.capture_frames()

    @host_only
    def get_images(self):
        if self._images is None:
            raise RuntimeError("Images have not yet been aquired")

        return self._images

    @host_only
    def run_once(self) -> None:
        logger.info("Starting camera measurement")
        self.start_camera_measurement()

        logger.info("Camera measurement completed")

        images = self.get_images()
        logger.info("Took %i images", len(images))

        timestamps, image_data = zip(*images)

        self.timestamps.push(np.array(timestamps))
        self.images.push(np.array(image_data))


MOTCameraMeasurementExp = make_fragment_scan_exp(MOTCameraMeasurement)
