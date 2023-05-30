import logging
import time
from typing import Dict
from typing import List
from typing import Tuple
from typing import Type

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

from repository.lib.constants import CHAMBER_2_HORIZONTAL_CAMERA_DEFAULTS
from repository.lib.constants import CHAMBER_2_VERTICAL_CAMERA_DEFAULTS


logger = logging.getLogger(__name__)


class CameraFrag(Fragment):
    """
    Class to control a GeniCAM compatible camera (tested with the FLIR-Blackfly
    S)

    To use this class, inherit from it and populate the class variables below.
    """

    default_features: Dict
    "Dict of features to initialise this camera with"

    monitor_dataset_key: str
    """
    Name of broadcast dataset to update with the latest image

    This Fragment does not have an output channel by default - it's up to you to
    do something useful with the images from your consumer code. This monitor
    dataset is not archived and is only for viewing while the experiment is
    running - don't rely on it for data taking!
    """

    monitor_dataset_description: str
    "Description for the monitor applet"

    camera_id: str
    """The camera's ID string for connecting via Aravis

    To find this, run `arv-tool` (part of Aravis which is in the AION ARTIQ
    environments) from a computer on the same LAN as the camera.
    """

    @classmethod
    def _validate_class_attrs(cls):
        attrs = [
            "default_features",
            "monitor_dataset_key",
            "monitor_dataset_description",
            "camera_id",
        ]
        for attr in attrs:
            if not hasattr(cls, attr):
                raise TypeError(
                    f"""
                    Missing class attribute {attr}

                    You must subclass the CameraFrag class and populate all the class attributes in your implementation
                    """.strip()
                )

    def __init__(self, *args, **kwargs):
        self._validate_class_attrs()
        super().__init__(*args, **kwargs)

    def build_fragment(self):
        for feature, value in self.default_features.items():
            self.setattr_param(feature, FloatParam, feature, default=value)

        self.setattr_device("ccb")

    def host_setup(self):
        # This import happens here because, for some reason, importing the
        # gi.repository Aravis (which happens in python-aravis) breaks if you do
        # it from multiple processes at the same time, which ARTIQ will trigger
        # when scanning for experiments
        from aravis import Camera

        # Open the monitoring applet
        self.set_dataset(
            self.monitor_dataset_key,
            np.array([[0.0]]),
            broadcast=True,
            persist=False,
            archive=False,
        )
        self.ccb.issue(
            "create_applet",
            self.monitor_dataset_description,
            f"${{artiq_applet}}image {self.monitor_dataset_key}",
        )

        self.cam = Camera(
            self.camera_id,
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

        for feature in self.default_features.keys():
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
        logger.info("Triggering measurement")
        self.cam.trigger()

    @host_only
    def get_frames(self, timeout=0.0) -> List[Tuple[int, ArrayLike]]:
        logger.info("Reading out frames. Expecting %d images", self.num_images)
        out = []
        for _ in range(self.num_images):
            try:
                out.append(self._get_one_frame_without_monitor_update(timeout=timeout))

            except TimeoutError:
                logger.warning(
                    "Expected %d images but only got %d", self.num_images, len(out)
                )
                break

        logger.info("Readout completed with %d images", len(out))

        self.cam.stop_acquisition()

        self._update_monitor(out[-1][1])

        return out

    @host_only
    def get_one_frame(self, timeout=0.0) -> Tuple[int, ArrayLike]:
        ts, img = self._get_one_frame_without_monitor_update(timeout=timeout)
        self._update_monitor(img)
        return ts, img

    @host_only
    def _get_one_frame_without_monitor_update(
        self, timeout=0.0
    ) -> Tuple[int, ArrayLike]:

        logger.info("_get_one_frame_without_monitor_update running")

        t_end = time.time() + timeout
        while True:
            frame = self.cam.try_pop_frame(True)

            if frame is not None and frame[0] is not None:
                return frame[0], np.array(frame[1], dtype="uint8")

            if time.time() > t_end:
                raise TimeoutError(f"Image not received after {timeout}s")

            time.sleep(0.01)

    @host_only
    def _update_monitor(self, img):
        # convert to int instead of uint8 for plotting
        self.set_dataset(
            self.monitor_dataset_key,
            np.array(img).astype("int"),
            broadcast=True,
            persist=False,
            archive=False,
        )


class Chamber2HorizontalCamera(CameraFrag):
    default_features = CHAMBER_2_HORIZONTAL_CAMERA_DEFAULTS
    monitor_dataset_key = "latest_ch2_horiz_image"
    monitor_dataset_description = "Chamber 2 horizontal camera"
    camera_id = "FLIR-Blackfly S BFS-PGE-50S5M-22018873"


class Chamber2VerticalCamera(CameraFrag):
    default_features = CHAMBER_2_VERTICAL_CAMERA_DEFAULTS
    monitor_dataset_key = "latest_ch2_vert_image"
    monitor_dataset_description = "Chamber 2 vertical camera"
    camera_id = "FLIR-Blackfly S BFS-PGE-50S5M-22018872"


class MonitorCamera(ExpFragment):
    camera_class: Type[CameraFrag]

    def __init__(self, managers_or_parent, *args, **kwargs):
        if not hasattr(self, "camera_class"):
            raise TypeError("Please specify camera_class by overriding this class")
        super().__init__(managers_or_parent, *args, **kwargs)

    def build_fragment(self):
        self.setattr_result("timestamp", IntChannel, display_hints={"priority": -1})
        self.timestamp: IntChannel

        self.setattr_result("image", OpaqueChannel)
        self.image: OpaqueChannel

        self.setattr_fragment("camera", self.camera_class)
        self.camera: CameraFrag

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
        self.image.push(image_data)

        t_end = time.time()

        time.sleep(max(self.delay.get() - (t_end - t_start), 0))


class MonitorChamber2HorizCamera(MonitorCamera):
    camera_class = Chamber2HorizontalCamera


class MonitorChamber2VertCamera(MonitorCamera):
    camera_class = Chamber2VerticalCamera


MonitorChamber2HorizCamera = make_fragment_scan_exp(MonitorChamber2HorizCamera)  # type: ignore
MonitorChamber2VertCamera = make_fragment_scan_exp(MonitorChamber2VertCamera)  # type: ignore
