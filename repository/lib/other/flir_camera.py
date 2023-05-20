import logging
import time
from typing import List
from typing import Tuple

import numpy as np
from numpy.typing import ArrayLike


logger = logging.getLogger(__name__)


class Chamber2Camera:
    def __init__(self, num_images, exposure_us, delay_ms):
        # This import happens here because, for some reason, importing the
        # gi.repository Aravis (which happens in python-aravis) breaks if you do
        # it from multiple processes at the same time, which ARTIQ will trigger
        # when scanning for experiments
        from aravis import Camera

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

    def capture_frames(self) -> List[Tuple[int, ArrayLike]]:
        self.cam.start_acquisition_continuous(nb_buffers=self._buffer_depth)

        out = []
        while True:
            time.sleep(self._per_image_time)

            new_frame = self.cam.try_pop_frame(True)
            if new_frame is not None:
                ts, frame = new_frame
                if ts is not None:
                    out.append((ts, frame))

            if len(out) == self._num_images:
                break

        self.cam.stop_acquisition()

        return out
