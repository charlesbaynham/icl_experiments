import logging
import time
from typing import List
from typing import Tuple

import numpy as np
from numpy.typing import ArrayLike


logger = logging.getLogger(__name__)


class Chamber2Camera:
    def __init__(self):
        # This import happens here because, for some reason, importing the
        # gi.repository Aravis (which happens in python-aravis) breaks if you do
        # it from multiple processes at the same time, which ARTIQ will trigger
        # when scanning for experiments
        from aravis import Camera

        self.cam = Camera(
            "FLIR-Blackfly S BFS-PGE-50S5M-22018873", loglevel=logging.INFO
        )
        self.cam.set_feature("ExposureAuto", "Off")

    def ready_for_trigger(self, exposure_us, num_images):
        self.num_images = num_images
        self.cam.set_exposure_time(exposure_us)
        self.cam.start_acquisition_trigger(nb_buffers=num_images)

    def trigger(self):
        self.cam.trigger()

    def get_frames(self) -> List[Tuple[int, ArrayLike]]:
        out = []
        for _ in range(self.num_images):
            new_frame = self.cam.try_pop_frame(True)
            if new_frame is not None and new_frame[0] is not None:
                out.append(new_frame)
            else:
                logger.warning(
                    "Expected %d images but only got %d", self.num_images, len(out)
                )

        self.cam.stop_acquisition()

        return out
