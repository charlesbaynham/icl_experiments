import logging
import time
from typing import List
from typing import Tuple

import aravis
import numpy as np
from aravis import Camera
from artiq.coredevice.core import Core
from artiq.experiment import host_only
from artiq.experiment import rpc
from ndscan.experiment import Fragment
from ndscan.experiment.parameters import FloatParam
from ndscan.experiment.parameters import FloatParamHandle
from ndscan.experiment.parameters import IntParam
from ndscan.experiment.parameters import IntParamHandle


logger = logging.getLogger(__name__)


class Chamber2Camera:
    def __init__(self, num_images, exposure_us, delay_ms):
        if delay_ms < 20:
            raise ValueError(
                "The camera cannot support a frame rate faster than 20ms per frame"
            )

        self.cam = Camera(
            "FLIR-Blackfly S BFS-PGE-50S5M-22018873", loglevel=logging.INFO
        )
        self.cam.set_frame_rate(1 / (1e-3 * delay_ms))
        self.cam.set_exposure_time(exposure_us)

        self._num_images = num_images
        self._buffer_depth = num_images + 10
        self._per_image_time = max([1e-6 * exposure_us, 1e-3 * delay_ms])

    def capture_frames(self) -> List[Tuple[int, np.array]]:
        self.cam.start_acquisition_continuous(nb_buffers=self._buffer_depth)

        out = []
        while True:
            time.sleep(self._per_image_time)

            ts, frame = self.cam.try_pop_frame(True)
            if ts is not None:
                out.append((ts, frame))

            if len(out) == self._num_images:
                break

        self.cam.stop_acquisition()

        return out


class MOTCameraMeasurement(Fragment):
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

    def host_setup(self):
        self.camera_driver = Chamber2Camera(
            num_images=self.number_images.get(),
            exposure_us=1e6 * self.exposure.get(),
            delay_ms=1e3 * self.image_delay.get(),
        )
        self.images = None
        return super().host_setup()

    @rpc
    def start_camera_measurement(self):
        """
        Start measuring images using pre-defined camera settings

        When finished, images will be available via :meth:`.get_images()`
        """
        self.images = self.camera_driver.capture_frames()

    @host_only
    def get_images(self):
        if self.images is None:
            raise RuntimeError("Images have not yet been aquired")

        return self.images
