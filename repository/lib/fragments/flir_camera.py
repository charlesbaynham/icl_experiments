import logging
import time
from typing import List
from typing import Tuple

import numpy as np
from artiq.experiment import host_only
from artiq.experiment import rpc
from ndscan.experiment import ExpFragment
from ndscan.experiment import Fragment
from ndscan.experiment.entry_point import make_fragment_scan_exp
from ndscan.experiment.parameters import FloatParam
from ndscan.experiment.parameters import FloatParamHandle
from ndscan.experiment.result_channels import IntChannel
from ndscan.experiment.result_channels import OpaqueChannel
from numpy.typing import ArrayLike

from repository.lib.constants import CHAMBER_2_CAMERA


logger = logging.getLogger(__name__)


class Chamber2Camera(Fragment):
    def build_fragment(self):
        pass

    def host_setup(self):
        # This import happens here because, for some reason, importing the
        # gi.repository Aravis (which happens in python-aravis) breaks if you do
        # it from multiple processes at the same time, which ARTIQ will trigger
        # when scanning for experiments
        from aravis import Camera

        self.cam = Camera(
            "FLIR-Blackfly S BFS-PGE-50S5M-22018873",
            loglevel=logger.getEffectiveLevel(),
        )

        # Set sensible defaults. The user might change these
        self.cam.set_feature("ExposureAuto", "Off")
        self.cam.set_feature("GainAuto", "Off")
        self.cam.set_feature("ExposureTime", 1000)
        self.cam.set_feature("Gain", 20)

        for feature, value in CHAMBER_2_CAMERA.items():
            self.cam.set_feature(feature, value)

        return super().host_setup()

    @rpc(flags={"async"})
    def ready_for_trigger(self, exposure_us, num_images):
        self.num_images = num_images
        self.cam.set_exposure_time(exposure_us)
        self.cam.start_acquisition_trigger(nb_buffers=num_images)

    @rpc(flags={"async"})
    def trigger(self):
        self.cam.trigger()

    @host_only
    def get_frames(self) -> List[Tuple[int, ArrayLike]]:
        out = []
        for _ in range(self.num_images):
            new_frame = self.cam.try_pop_frame(True)
            if new_frame is not None and new_frame[0] is not None:
                ts, data = new_frame
                out.append((ts, np.array(data)))
            else:
                logger.warning(
                    "Expected %d images but only got %d", self.num_images, len(out)
                )

        self.cam.stop_acquisition()

        return out


class MonitorChamber2Camera(ExpFragment):
    def build_fragment(self):
        self.setattr_result("timestamp", IntChannel)
        self.timestamp: IntChannel

        self.setattr_result("image", OpaqueChannel)
        self.image: OpaqueChannel

        self.setattr_fragment("camera", Chamber2Camera)
        self.camera: Chamber2Camera

        self.setattr_device("scheduler")
        self.setattr_device("ccb")

        self.setattr_param(
            "exposure", FloatParam, description="Exposure", unit="us", default=1000e-6
        )
        self.setattr_param(
            "delay", FloatParam, description="Delay", unit="ms", default=500e-3
        )

        self.exposure: FloatParamHandle
        self.delay: FloatParamHandle

        try:
            image_dataset = f"ndscan.rid_{self.scheduler.rid}.point.image"
            self.ccb.issue(
                "create_applet",
                "Chamber 2 camera",
                f"${{artiq_applet}}image {image_dataset}",
            )
        except AttributeError:
            pass

    @host_only
    def run_once(self) -> None:
        logger.info("Starting camera measurement")
        self.camera.ready_for_trigger(self.exposure.get() * 1e6, 1)

        self.camera.trigger()

        acquisition_delay = self.exposure.get() + 10e-3

        time.sleep(acquisition_delay)

        logger.info("Camera measurement completed")

        images = self.camera.get_frames()

        logger.info("Took %i images", len(images))

        timestamps, image_data = zip(*images)

        self.timestamp.push(timestamps[0])
        self.image.push(image_data[0])

        time.sleep(max(self.delay.get() - acquisition_delay, 0))


MonitorChamber2Camera = make_fragment_scan_exp(MonitorChamber2Camera)  # type: ignore
