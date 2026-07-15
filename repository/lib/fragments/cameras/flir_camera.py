import abc
import logging
import time
from typing import TYPE_CHECKING
from typing import Dict
from typing import List
from typing import Tuple
from typing import Type

import numpy as np
from artiq.coredevice.ttl import TTLOut
from artiq.language import delay
from artiq.language import host_only
from artiq.language import kernel
from artiq.language import portable
from artiq.language import rpc
from ndscan.experiment import ExpFragment
from ndscan.experiment import Fragment
from ndscan.experiment.parameters import BoolParam
from ndscan.experiment.parameters import BoolParamHandle
from ndscan.experiment.parameters import FloatParam
from ndscan.experiment.parameters import FloatParamHandle
from ndscan.experiment.result_channels import FloatChannel
from ndscan.experiment.result_channels import IntChannel
from ndscan.experiment.result_channels import OpaqueChannel
from numpy.typing import ArrayLike

from repository.lib.constants import CHAMBER_2_HORIZONTAL_CAMERA_DEFAULTS
from repository.lib.constants import CHAMBER_2_VERTICAL_CAMERA_DEFAULTS
from repository.lib.constants import FLIR_CAMERA_TRIGGER_PREEMPT_TIME

if TYPE_CHECKING:
    from aravis import Camera


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

    camera_device: str
    """The camera's device name in device_db

    To add a camera to device_db, you'll need the camera's unique ID which you
    can find by running `arv-tool` (part of Aravis which is in the AION ARTIQ
    environments) from a computer on the same LAN as the camera.
    """

    ttl_trigger_device: str
    """The ttl line to use for hardware triggering.

    Only used if "hardware_trigger=True" was passed to build_fragment
    """

    @classmethod
    def _validate_class_attrs(cls):
        attrs = [
            "default_features",
            "monitor_dataset_key",
            "monitor_dataset_description",
            "camera_device",
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

    def build_fragment(self, hardware_trigger=False):
        for feature, value in self.default_features.items():
            self.setattr_param(feature, FloatParam, feature, default=value)

        self.setattr_param(
            "save_raw_images",
            BoolParam,
            description="Save raw camera data",
            default=False,
        )
        self.save_raw_images: BoolParamHandle

        self.setattr_device("ccb")

        self.hardware_trigger = hardware_trigger

        if hardware_trigger:
            self.setattr_device("core")
            self.ttl_trigger: TTLOut = self.get_device(self.ttl_trigger_device)

        # Kernel variables
        self.debug_enabled = logger.isEnabledFor(logging.DEBUG)
        self.exposure = 0.0

        # %% Kernel invariants
        kernel_invariants = getattr(self, "kernel_invariants", set())
        self.kernel_invariants = kernel_invariants | {
            "debug_enabled",
            # "exposure",
        }

    def host_setup(self):
        self.save_raw = self.save_raw_images.get()

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

        self.cam: Camera = self.get_device(self.camera_device)
        # The device manager caches the camera across pause/resume, but
        # host_cleanup shut it down - bring the connection back
        self.cam.reopen()

        # Set sensible defaults. The user might change these
        self.cam.set_feature("ExposureMode", "Timed")
        self.cam.set_feature("TriggerSource", "Software")
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
        if hasattr(self, "cam"):
            self.cam.shutdown()

        super().host_cleanup()

    @portable
    def ready_for_trigger(self, exposure_us, num_images):
        """
        Prepare the camera for taking images

        Image acquisition should then be triggered via :meth:`.trigger` and read
        out by :meth:`.get_frames`.
        """
        # Save exposure time - this is used for hardware triggering to determine the TTL pulse length
        self.exposure = 1e-6 * exposure_us

        # Set the rest of the parameters on the camera itself via an RPC
        self._ready_for_trigger_rpc(exposure_us, num_images)

    @rpc(flags={"async"})
    def _ready_for_trigger_rpc(self, exposure_us, num_images):
        self.num_images = num_images

        # In hardware trigger mode, the exposure time is determined by the
        # length of the TTL pulse
        if not self.hardware_trigger:
            self.cam.set_exposure_time(exposure_us)

        self._start_acquisition_selectable_trigger(
            nb_buffers=num_images, hardware_trigger=self.hardware_trigger
        )

        # Read out any images still in the buffer
        while self.cam.try_pop_frame() is not None:
            pass

    @host_only
    def _start_acquisition_selectable_trigger(
        self, nb_buffers=1, hardware_trigger=False
    ):
        """
        Reimplementation of PyAravis's function but allowing hardware triggering
        """

        self.cam.set_feature("AcquisitionMode", "Continuous")  # no acquisition limits
        self.cam.set_feature("TriggerMode", "On")  # Not documented but necesary

        if hardware_trigger:
            self.cam.set_feature("ExposureMode", "TriggerWidth")
            self.cam.set_feature("TriggerSource", "Line0")
        else:
            self.cam.set_feature("ExposureMode", "Timed")
            self.cam.set_feature("TriggerSource", "Software")

        self.cam.start_acquisition(nb_buffers)

    @kernel
    def trigger(self):
        """
        Trigger a measurement now

        The camera must have been set up via :meth:`.ready_for_trigger` first.

        In hardware trigger mode, this advances the timeline by the exposure
        time. In software trigger mode, it calls an RPC.
        """
        if self.hardware_trigger:
            if self.debug_enabled:
                logger.info(
                    "Triggering hardware measurement with exposure = %.1fus",
                    1e6 * self.exposure,
                )
            self._hardware_trigger()  # TODO: This won't compile in software triggering mode - see e.g. red shelving @ 6e62e2
        else:
            if self.debug_enabled:
                logger.info("Triggering software measurement")
            self._software_trigger()

    @kernel
    def _hardware_trigger(self):
        """
        Trigger the camera using a TTL pulse

        Note: this adds a constant `FLIR_CAMERA_TRIGGER_PREEMPT_TIME` of pre-empt
        time to the exposure. If you are imaging a steady-state MOT instead of a
        fluorescence pulse, this will result in a increased signal.

        Writes into the past by the pre-empt time and advances the timeline by
        the camera exposure time
        """
        delay(-FLIR_CAMERA_TRIGGER_PREEMPT_TIME)
        self.ttl_trigger.pulse(self.exposure + FLIR_CAMERA_TRIGGER_PREEMPT_TIME)
        delay(FLIR_CAMERA_TRIGGER_PREEMPT_TIME)

    @rpc(flags={"async"})
    def _software_trigger(self):
        self.cam.trigger()

    @host_only
    def get_frames(self, timeout=0.0) -> List[Tuple[int, ArrayLike]]:
        logger.debug("Reading out frames. Expecting %d images", self.num_images)
        out = []
        for _ in range(self.num_images):
            try:
                out.append(self._get_one_frame_without_monitor_update(timeout=timeout))

            except TimeoutError:
                logger.warning(
                    "Expected %d images but only got %d", self.num_images, len(out)
                )
                break

        logger.debug("Readout completed with %d images", len(out))

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
        logger.debug("_get_one_frame_without_monitor_update running")

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
        # convert to int instead of uint8 for saving
        if self.save_raw:
            data = np.array(img).astype("int")
        else:
            data = np.array([[0]]).astype("int")

        # convert to int instead of uint8 for plotting
        self.set_dataset(
            self.monitor_dataset_key,
            data,
            broadcast=True,
            persist=False,
            archive=False,
        )


class Chamber2HorizontalCamera(CameraFrag):
    default_features = CHAMBER_2_HORIZONTAL_CAMERA_DEFAULTS
    monitor_dataset_key = "latest_ch2_horiz_image"
    monitor_dataset_description = "Chamber 2 horizontal camera"
    camera_device = "flir_camera_ch2_horizontal"
    ttl_trigger_device = "ttl_camera_trigger_horizontal"


class Chamber2VerticalCamera(CameraFrag):
    default_features = CHAMBER_2_VERTICAL_CAMERA_DEFAULTS
    monitor_dataset_key = "latest_ch2_vert_image"
    monitor_dataset_description = "Chamber 2 vertical camera"
    camera_device = "flir_camera_ch2_vertical"
    ttl_trigger_device = "ttl_camera_trigger_vertical"


class MonitorCameraExpBase(ExpFragment, abc.ABC):
    @property
    @abc.abstractmethod
    def camera_class(self) -> Type[CameraFrag]:
        """
        The camera class that this experiment will monitor. Must be overridden
        by subclasses as a class property
        """

    def build_fragment(self):
        self.setattr_result("timestamp", IntChannel, display_hints={"priority": -1})
        self.timestamp: IntChannel

        self.setattr_result("image", OpaqueChannel)
        self.image: OpaqueChannel

        self.setattr_result("image_sum", FloatChannel)
        self.image_sum: FloatChannel

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

        self.setattr_param_rebind("save_raw_images", self.camera, default=True)

        self.exposure: FloatParamHandle
        self.delay: FloatParamHandle

    @host_only
    def run_once(self) -> None:
        t_start = time.time()

        logger.info("Starting camera measurement")
        self.camera.ready_for_trigger(self.exposure.get() * 1e6, 1)

        self.camera._software_trigger()

        logger.info("Camera measurement completed")

        timestamp, image_data = self.camera.get_one_frame(
            timeout=1 + self.exposure.get()
        )

        pixel_sum = np.sum(image_data.flat)

        self.timestamp.push(timestamp)
        self.image.push(image_data)
        self.image_sum.push(pixel_sum)

        t_end = time.time()

        time.sleep(max(self.delay.get() - (t_end - t_start), 0))


MonitorCameraExp = MonitorCameraExpBase
