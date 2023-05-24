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
        for feature, value in CHAMBER_2_CAMERA.items():
            self.setattr_param(feature, FloatParam, feature, default=value)

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

        max_height = self.cam.get_feature("HeightMax")
        max_width = self.cam.get_feature("WidthMax")

        self.cam.set_feature("OffsetX", 0)
        self.cam.set_feature("OffsetY", 0)
        self.cam.set_feature("Height", max_height)
        self.cam.set_feature("Width", max_width)

        for feature in CHAMBER_2_CAMERA.keys():
            value = getattr(self, feature).get()
            self.cam.set_feature(feature, value)

        # Reset the camera timestamp in setup rather than ready_for_trigger so
        # that timestamps increase when scanned from a kernel
        self.cam.execute_command("TimestampReset")

        return super().host_setup()

    def host_cleanup(self):
        self.cam.shutdown()

        super().host_cleanup()

    @rpc(flags={"async"})
    def ready_for_trigger(self, exposure_us, num_images):
        """
        Prepare the camera for taking images

        Image acquisition should then be triggered via :meth:`.trigger` and read
        out by :meth:`.get_frames`.
        """
        self.num_images = num_images
        self.cam.set_exposure_time(exposure_us)

        self.cam.start_acquisition_trigger(nb_buffers=num_images)

        # Read out any images still in the buffer
        while self.cam.try_pop_frame() is not None:
            pass

    @rpc(flags={"async"})
    def trigger(self):
        """
        Trigger a measurement now

        The camera must have been set up via :meth:`.ready_for_trigger` first.
        """
        self.cam.trigger()

    @host_only
    def get_frames(self, timeout=0.0) -> List[Tuple[int, ArrayLike]]:
        out = []
        for _ in range(self.num_images):
            try:
                out.append(self.get_one_frame(timeout=timeout))

            except TimeoutError:
                logger.warning(
                    "Expected %d images but only got %d", self.num_images, len(out)
                )
                break

        self.cam.stop_acquisition()

        return out

    @host_only
    def get_one_frame(self, timeout=0.0) -> Tuple[int, ArrayLike]:
        t_end = time.time() + timeout
        while True:
            frame = self.cam.try_pop_frame(True)

            if frame is not None and frame[0] is not None:
                return frame[0], np.array(frame[1], dtype="uint8")

            if time.time() > t_end:
                raise TimeoutError(f"Image not received after {timeout}s")

            time.sleep(0.01)


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
        t_start = time.time()

        logger.info("Starting camera measurement")
        self.camera.ready_for_trigger(self.exposure.get() * 1e6, 1)

        self.camera.trigger()

        logger.info("Camera measurement completed")

        timestamp, image_data = self.camera.get_one_frame(
            timeout=1 + self.exposure.get()
        )

        self.timestamp.push(timestamp)

        # convert to int instead of uint8 for plotting
        self.image.push(np.array(image_data).astype("int"))

        t_end = time.time()

        time.sleep(max(self.delay.get() - (t_end - t_start), 0))


MonitorChamber2Camera = make_fragment_scan_exp(MonitorChamber2Camera)  # type: ignore
