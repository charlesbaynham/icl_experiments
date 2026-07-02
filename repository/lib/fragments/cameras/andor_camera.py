import abc
import logging
import typing as ty

import numpy as np
from andor_artiq_ndsp.driver import AndorDriver
from artiq.coredevice.core import Core
from artiq.coredevice.grabber import Grabber
from artiq.coredevice.ttl import TTLOut
from artiq.experiment import TArray
from artiq.experiment import TBool
from artiq.experiment import TFloat
from artiq.experiment import TInt32
from artiq.language import delay_mu
from artiq.language import host_only
from artiq.language import kernel
from artiq.language import portable
from artiq.language import rpc
from ndscan.experiment import Fragment
from ndscan.experiment.parameters import BoolParam
from ndscan.experiment.parameters import BoolParamHandle
from ndscan.experiment.parameters import FloatParam
from ndscan.experiment.parameters import FloatParamHandle
from ndscan.experiment.parameters import IntParam
from ndscan.experiment.parameters import IntParamHandle
from numpy import int64

from repository.lib import constants

logger = logging.getLogger(__name__)


class AndorNoImageAvailable(Exception):
    pass


class AndorCameraConfig(Fragment, abc.ABC):
    """
    A configuration object that contains settings for the Andor camera + Grabber

    This object is responsible for calculating the position of ROIs, defining
    the number of images, etc. These can be hard-coded, set by parameters or
    calculated on the fly, as required.

    This is an abstract base class - concrete implementations must implement the
    abstract methods below.
    """

    num_andor_images: int = None  # type: ignore
    "How many images will the Andor driver read out"
    num_images_per_series: int = None  # type: ignore
    "How many images will the Andor driver read out in each series"
    num_grabber_rois: int = None  # type: ignore
    "How many ROIs in each image for the Grabber"
    num_grabber_readouts: int = None  # type: ignore
    "How many images will the Grabber read out"

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

        if self.num_andor_images is None:
            raise ValueError("num_andor_images must be set in subclass")

        if self.num_images_per_series is None:
            raise ValueError("num_images_per_series must be set in subclass")

        if self.num_grabber_rois is None:
            raise ValueError("num_grabber_rois must be set in subclass")

        if self.num_grabber_readouts is None:
            raise ValueError("num_grabber_readouts must be set in subclass")

    def host_setup(self):
        super().host_setup()

        if self.num_grabber_rois != len(self.get_rois()):
            raise ValueError(
                "num_grabber_rois must be equal to the number of ROIs returned by get_rois()"
            )

        for roi in self.get_rois():
            if len(roi) != 4:
                raise ValueError(
                    "Each ROI returned by get_rois() must be a list of 4 integers: [x0, y0, x1, y1]"
                )

    def build_fragment(self):
        pass

    @portable
    @abc.abstractmethod
    def get_rois(self) -> TArray(TInt32, 2):  # pyright: ignore[reportInvalidTypeForm]
        """
        Get the list of desired grabber ROIs

        Returns an array of size (N, 4) where each line is (x0, y0, x1, y1)

        The output array MUST always have the same length N: changing this
        dynamically is not supported and will break things.
        """

        # TODO: rewrite to use a class:
        # class ROI:
        #     x0: int = 0
        #     y0: int = 0
        #     x1: int = 0
        #     y1: int = 0

    @portable
    def calculate_area_from_roi(self, roi):
        """
        Calculate area of an ROI

        Parameters:
        roi (List[int]): List of 4 integers [x0, y0, x1, y1]

        Returns:
            int: Area of the ROI in pixels
        """
        return (roi[2] - roi[0]) * (roi[3] - roi[1])


class FastKineticsCameraConfig(AndorCameraConfig):
    """
    Base configuration for Andor camera in fast kinetics mode.

    Subclasses must set `fast_kinetics_height`, `fast_kinetics_offset`,
    and `fast_kinetics_num_shots` as class attributes.

    Adds parameters for fast kinetics height, offset and time between shots.
    """

    fast_kinetics_height: int = None  # type: ignore
    fast_kinetics_offset: int = None  # type: ignore
    fast_kinetics_num_shots: int = None  # type: ignore

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

        if self.fast_kinetics_height is None:
            raise ValueError("fast_kinetics_height must be set in subclass")
        if self.fast_kinetics_offset is None:
            raise ValueError("fast_kinetics_offset must be set in subclass")
        if self.fast_kinetics_num_shots is None:
            raise ValueError("fast_kinetics_num_shots must be set in subclass")

    def get_fast_kinetics_offset(self) -> TInt32:  # pyright: ignore[reportInvalidTypeForm]
        """Fast-kinetics readout-window offset (first-shot top row) in pixels.

        The window's top edge on the 512-row sensor; the readout frame is
        ``fast_kinetics_num_shots`` sub-frames of ``fast_kinetics_height`` rows
        starting here. Configs that fix the window return the class attribute;
        configs that expose it as a scannable parameter (so the window can
        follow launched clouds up the sensor) override this to return the
        param's current value.
        """
        return self.fast_kinetics_offset

    def build_fragment(self):
        super().build_fragment()

        # self.setattr_param(
        #     "fast_kinetics_height",
        #     IntParam,
        #     "Fast kinetics height",
        #     default=self.fast_kinetics_height,
        #     min=0,
        #     max=512,
        # )
        # self.fast_kinetics_height: IntParamHandle

        # self.setattr_param(
        #     "fast_kinetics_offset",
        #     IntParam,
        #     "Fast kinetics offset",
        #     default=self.fast_kinetics_offset,
        #     min=0,
        #     max=512,
        # )
        # self.fast_kinetics_offset: IntParamHandle

        self.setattr_param(
            "fast_kinetics_time_between_shots",
            FloatParam,
            "Fast kinetics time between shots",
            default=3.5e-3,
            unit="ms",
            min=0,
        )
        self.fast_kinetics_time_between_shots: FloatParamHandle
        # Note that fast_kinetics_time_between_shots is not equal to the
        # "exposure time" described in the Andor manual!
        # fast_kinetics_time_between_shots == exposure time +
        # fast_kinetics_shift_time

    @staticmethod
    def _calculate_rois(height, offset, num_images, x0, y0, x1, y1, excited_shift=0):
        """
        Calculate grabber ROIs for fast kinetics mode.

        Given an ROI (x0, y0, x1, y1) on the full image, returns a list of ROIs
        in (x0, y0, x1, y1) format, one per fast kinetics shot.

        Args:
            height: Fast kinetics subarea height in pixels
            offset: Fast kinetics offset in pixels
            num_images: Number of fast kinetics images
            x0, y0, x1, y1: ROI coordinates on the full image
            excited_shift: Additional shift for excited state compensation (default 0)

        Returns:
            List of [x0, y0, x1, y1] ROIs
        """
        return [
            [
                x0,
                y0 + i * (height - excited_shift) - offset,
                x1,
                y1 + i * (height - excited_shift) - offset,
            ]
            for i in range(num_images)
        ]


class AndorCameraControl(Fragment):
    """
    Control the Andor camera and associated shutters / triggers

    This Fragment handles triggering and readout (via Grabber). Setup is not yet
    controlled.

    TODO: Add Andor camera parameter control

    The camera's ROI / fast-kinetics behaviour is supplied via an
    :class:`AndorCameraConfig` instance, which the caller constructs and passes
    in. See :class:`AndorCameraConfig` (and subclasses such as
    :class:`FastKineticsCameraConfig`) for the available options.

    Parameters:
    camera_config (AndorCameraConfig): Required. Describes the ROI layout and,
        for fast-kinetics modes, the number of sub-frames and their geometry.
    add_pre_trigger_delay (bool): Whether to add a delay before triggering the
        camera.
    """

    def build_fragment(
        self,
        camera_config: AndorCameraConfig = None,  # type: ignore
        add_pre_trigger_delay=True,
    ):
        self.setattr_device("core")
        self.core: Core

        if camera_config is None:
            raise ValueError("Must provide AndorCameraConfig to AndorCameraControl")

        self.andor_camera_config = camera_config

        self.setattr_device("grabber0")
        self.grabber: Grabber = self.grabber0  # type: ignore

        self.ttl_trigger: TTLOut = self.get_device("ttl_camera_trigger_andor")
        self.ttl_shutter: TTLOut = self.get_device("ttl_shutter_andor")

        # %% Params

        self.setattr_param(
            "shutter_delay",
            FloatParam,
            "Time to allow for shutter to open before imaging",
            default=constants.ANDOR_CAMERA_SHUTTER_OPEN_TIME,
            unit="ms",
            min=0.0,
        )
        self.shutter_delay: FloatParamHandle

        self.setattr_param(
            "pre_trigger_delay",
            FloatParam,
            "Time to allow for camera triggering to be enabled",
            default=constants.ANDOR_CAMERA_TRIGGER_ENABLE_TIME,
            unit="us",
            min=0.0,
        )
        self.pre_trigger_delay: FloatParamHandle

        if not add_pre_trigger_delay:
            self.override_param("pre_trigger_delay", 0.0)

        self.setattr_param(
            "use_andor_driver",
            BoolParam,
            default=True,
            description="andor driver mode",
        )
        self.use_andor_driver: BoolParamHandle

        self.setattr_param(
            "save_raw_andor_image",
            BoolParam,
            default=False,
            description="save raw andor image",
        )
        self.save_raw_andor_image: BoolParamHandle

        self.setattr_param(
            "baseline_clamp_mode",
            BoolParam,
            default=True,
            description="Baseline clamp mode",
        )
        self.baseline_clamp_mode: BoolParamHandle

        self.setattr_param(
            "cam_roi_x0",
            IntParam,
            "Camera ROI x0",
            default=0,
            min=0,
            max=512,
        )
        self.setattr_param(
            "cam_roi_x1",
            IntParam,
            "Camera ROI x1",
            default=512,
            min=0,
            max=512,
        )
        self.setattr_param(
            "cam_roi_y0",
            IntParam,
            "Camera ROI y0",
            default=0,
            min=0,
            max=512,
        )
        self.setattr_param(
            "cam_roi_y1",
            IntParam,
            "Camera ROI y1",
            default=512,
            min=0,
            max=512,
        )

        self.cam_roi_x0: IntParamHandle
        self.cam_roi_x1: IntParamHandle
        self.cam_roi_y0: IntParamHandle
        self.cam_roi_y1: IntParamHandle

        # %% Kernel variables

        if isinstance(camera_config, FastKineticsCameraConfig):
            self.fast_kinetics_num_shots = camera_config.fast_kinetics_num_shots
        else:
            self.fast_kinetics_num_shots = 1
        self.fast_kinetics_mode = self.fast_kinetics_num_shots > 1

        self.debug_enabled = logger.isEnabledFor(logging.DEBUG)

        self.kernel_invariants = getattr(self, "kernel_invariants", set())
        self.kernel_invariants.add("debug_enabled")
        self.kernel_invariants.add("fast_kinetics_mode")
        self.kernel_invariants.add("fast_kinetics_num_shots")
        self.kernel_invariants.add("andor_requires_storage_frame")
        self.kernel_invariants.add("ttl_trigger")
        self.kernel_invariants.add("ttl_shutter")

    def host_setup(self):
        self.num_rois = len(self.andor_camera_config.get_rois())
        self.kernel_invariants.add("num_rois")

        self.fast_kinetics_shift_time = 0.0  # to prevent compilation errors
        # If the andor is in fast kinetics mode and the height of pixels to emit
        # is > 512, it will emit two frames onto Grabber instead of one. The
        # first will be "nonsense" (probably with some digital information that
        # the grabber isn't parsing) and the second will contain all the pixels,
        # up to a max of 1024 high (i.e. the image + storage EMCCDs).
        # See labbook entry 2024-06-11.
        self.andor_requires_storage_frame = self.fast_kinetics_mode and (
            ty.cast(
                FastKineticsCameraConfig, self.andor_camera_config
            ).fast_kinetics_height
            * self.fast_kinetics_num_shots
            > constants.ANDOR_SENSOR_HEIGHT
        )

        if self.use_andor_driver.get():
            self.cam: AndorDriver = self.get_device("andor_camera")
            if self.cam.get_status() == 20072:
                logger.warning("Andor still acquiring, stopping acquisition")
                self.cam.stop_acquisition()

            # Default the camera to NO EM gain. If the EMGainMixin has been
            # added to the experiment it will set the gain appropriately during
            # device_setup (which runs after all host_setups); without it, we
            # must ensure the camera does not retain EM gain that a previous
            # experiment may have left set in the hardware.
            self.cam.set_EMCCD_gain(0)

            self.set_roi()
            self.cam.set_baseline_clamp(self.baseline_clamp_mode.get())

            self.cam.set_shutter_open()

            if self.fast_kinetics_mode:
                logger.info("Setting up fast kinetics mode")
                self.cam.set_external_start_trigger()
                self.cam.set_fast_kinetics_mode()
                # Fast kinetics mode must be set up per shot, so we do this in _start_acquisition

                # Get the current time required to shift out one Fast Kinetics
                # region. The driver will initiate the vertical shift speed to the
                # fastest recommended. We need to know this because it will be added
                # to the "exposure time" specified in Fast Kinetics mode.

                self.fast_kinetics_shift_time = (
                    ty.cast(
                        FastKineticsCameraConfig, self.andor_camera_config
                    ).fast_kinetics_height
                    * self.cam.get_vsspeed()
                    * 1e-6
                )
                logger.info(
                    "fast_kinetics_shift_time = %.2f us",
                    self.fast_kinetics_shift_time * 1e6,
                )
                self.kernel_invariants.add("fast_kinetics_shift_time")

            else:
                self.fast_kinetics_shift_time = (
                    0.0  # This is unused, but is here to prevent compilation errors
                )
                logger.debug("Setting external exposure mode")
                self.cam.set_external_exposure_trigger()
                logger.debug("Setting continuous acquisition mode")
                self.cam.set_run_till_abort_mode()
                # Start the acquisition here: it'll run forever and we just
                # readout images as they come in
                self.cam.start_acquisition()

        super().host_setup()

    def host_cleanup(self):
        # The second statement in the if clause is here because if something
        # fails in host_setup of another fragment, it's possible for
        # host_cleanup to be called despite host_setup not having been called
        # yet:
        if self.use_andor_driver.get() and hasattr(self, "cam"):
            self.cam.stop_acquisition()
            self.cam.set_shutter_closed()
        super().host_cleanup()

    @host_only
    def set_roi(self):
        roi = {}

        if (
            self.cam_roi_x0.get() > 0
            or self.cam_roi_x1.get() < 512
            or self.cam_roi_y0.get() > 0
            or self.cam_roi_y1.get() < 512
        ):
            logger.warning(
                "Camera ROIs have been restricted: you might encounter this bug:"
            )
            logger.warning(
                "https://github.com/m-labs/artiq/issues/1369#issuecomment-904447252"
            )

        roi["hstart"] = int(self.cam_roi_x0.get())
        roi["hend"] = int(self.cam_roi_x1.get())
        roi["vstart"] = int(self.cam_roi_y0.get())
        roi["vend"] = int(self.cam_roi_y1.get())
        self.cam.set_roi(**roi)

    @rpc(flags={"async"})
    def start_acquisition_async(self):
        self.cam.start_acquisition()

    @rpc
    def start_acquisition(self):
        self.cam.start_acquisition()

    @rpc(flags={"async"})
    def setup_fast_kinetics_mode(self, offset_override: TInt32 = -1):
        # offset_override lets the caller supply a per-shot offset computed
        # kernel-side. Kernel writes to config attributes are NOT synced to the
        # host mid-kernel (only at kernel exit), so an async RPC reading
        # config.get_fast_kinetics_offset() would see the *previous* shot's
        # value; passing it as an explicit RPC argument crosses the boundary
        # correctly. -1 (the default, used by device_setup) means "read the
        # config accessor" - correct for the static and manual-offset cases.
        exposure_time = (
            ty.cast(
                FastKineticsCameraConfig, self.andor_camera_config
            ).fast_kinetics_time_between_shots.get()
            - self.fast_kinetics_shift_time
        )

        if exposure_time < 0:
            raise ValueError(
                "fast_kinetics_time_between_shots must be greater than the time required"
                f" to shift out one Fast Kinetics region = {1e6*self.fast_kinetics_shift_time:.3f} us"
            )

        config = ty.cast(FastKineticsCameraConfig, self.andor_camera_config)
        if offset_override >= 0:
            offset = offset_override
        else:
            offset = config.get_fast_kinetics_offset()
        height = config.fast_kinetics_height

        # The readout frame is num_shots stacked sub-frames of `height` rows
        # starting at `offset`; it must fit on the sensor.
        if offset < 0 or offset + self.fast_kinetics_num_shots * height > (
            constants.ANDOR_SENSOR_HEIGHT
        ):
            raise ValueError(
                "Fast-kinetics readout window does not fit the sensor: offset"
                f" {offset} + {self.fast_kinetics_num_shots} x height {height}"
                f" exceeds {constants.ANDOR_SENSOR_HEIGHT} rows"
            )

        self.cam.stop_acquisition()
        self.cam.setup_fast_kinetics_mode(
            num_acc=self.fast_kinetics_num_shots,
            subarea_height=height,
            exposure_time=exposure_time,
            offset=offset,
        )

    @kernel
    def device_setup(self) -> None:
        self.device_setup_subfragments()

        # If in fast kinetics mode we cannot acquire continuously, so trigger a
        # new acquisition each cycle
        if self.fast_kinetics_mode:
            self.setup_fast_kinetics_mode()
            self.start_acquisition_async()

        self.core.break_realtime()

        # Close the shutter and init the trigger

        self.ttl_shutter.off()
        delay_mu(int64(self.core.ref_multiplier))
        self.ttl_trigger.off()
        delay_mu(int64(self.core.ref_multiplier))
        self.ttl_shutter.output()
        delay_mu(int64(self.core.ref_multiplier))
        self.ttl_trigger.output()
        delay_mu(int64(self.core.ref_multiplier))

        # %% Setup ROIs

        mask = 0

        roi_config = self.andor_camera_config.get_rois()

        for i in range(self.num_rois):
            self.core.break_realtime()
            self.grabber.setup_roi(
                i,
                roi_config[i][0],
                roi_config[i][1],
                roi_config[i][2],
                roi_config[i][3],
            )
            mask = mask | (1 << i)

        # Enable appropriate ROIs
        self.grabber.gate_roi(mask)

    @kernel
    def reprogram_rois(self) -> None:
        """
        Re-read the config's ROIs and reprogram the grabber mid-shot.

        Re-issues exactly the ROI programming that :meth:`device_setup`
        performs at the start of the shot, re-reading
        ``self.andor_camera_config.get_rois()``. Use this to apply dynamically
        computed ROIs: the programming done at shot start necessarily uses the
        previous shot's positions, so configs that predict cloud positions
        during the shot need their ROIs re-written afterwards.

        Must run before the first camera frame of the shot reaches the
        grabber. Unlike :meth:`device_setup` this method does not call
        ``break_realtime`` - the caller is responsible for supplying enough
        timeline slack for the writes.
        """
        mask = 0

        roi_config = self.andor_camera_config.get_rois()

        for i in range(self.num_rois):
            self.grabber.setup_roi(
                i,
                roi_config[i][0],
                roi_config[i][1],
                roi_config[i][2],
                roi_config[i][3],
            )
            delay_mu(int64(self.core.ref_multiplier))
            mask = mask | (1 << i)

        # Enable appropriate ROIs
        self.grabber.gate_roi(mask)

    @kernel
    def device_cleanup(self) -> None:
        self.device_cleanup_subfragments()

        # Ensure the camera's protective shutter is closed
        self.core.break_realtime()
        self.ttl_shutter.off()

        # Disable the ROIs
        self.grabber.gate_roi(0x00)

    @kernel
    def set_shutter(self, state: TBool):  # type: ignore
        """
        Open or close the protective shutter

        This will be automatically closed at the end of a sequence if you
        forget, but you should close it immediately after use to avoid damaging
        the camera with lots of light while it's in EM gain mode.
        """
        self.ttl_shutter.set_o(state)

    @kernel
    def trigger(self, exposure: TFloat, control_shutter=False):  # type: ignore
        """
        Trigger an acquisition

        If `use_andor_driver` is enabled, the right trigger mode will be
        selected for you. Otherwise you must set it up yourself.

        If fast_kinetics_mode is enabled, the exposure setting will only control
        the shutter (if requested): the correct exposure must be set as
        `fast_kinetics_exposure_time`.

        You should call :meth:`~.save_data` to read out the configured ROI at
        the end of your sequence.

        If control_shutter == True, open the shutter <shutter_delay> in advance
        and then close if afterwards.

        ### Pre-trigger delay detail

        In normal mode:

        If this Fragment was built with add_pretrigger_delay == True, go back in
        time by <trigger_delay> then trigger the camera for <trigger_delay> +
        <exposure>. Otherwise, just expose the camera for <exposure>.

        In Fast Kinetics mode:

        The imaging sequence in Fast Kinetics mode is non-trivial and
        undocumented. Fast Kinetics mode is setup with a height and exposure
        time, defining a region that will be imaged. Clocking that region out
        takes:

        $$ t_{shift} = N_{rows} * t_{shift speed} $$

        When a sequence is triggered, the camera *immediately* begins clocking
        out one ROI, requiring $t_{shift}$ to complete. It then waits for
        $t_{exposure}$. It then repeats these two steps for a total of $N$
        shots.

        That means that you cannot take images during the first $t_{shift}$
        after triggering - surprising behaviour! We therefore will trigger the
        camera $t_{shift} + t_{pretrigger}$ before the cursor to allow for this
        shifting (as well as any other configured delay).

        ### Timeline

        Advances the timeline by the duration of the camera's exposure. Writes
        events into the past by up to $t_{shift} + t_{pretrigger}$.
        """

        if control_shutter:
            shutter_delay_mu = self.core.seconds_to_mu(self.shutter_delay.get())
            delay_mu(-shutter_delay_mu)
            self.ttl_shutter.on()
            delay_mu(shutter_delay_mu)

        pre_trigger_delay_mu = self.core.seconds_to_mu(self.pre_trigger_delay.get())
        exposure_mu = self.core.seconds_to_mu(exposure)

        if self.fast_kinetics_mode:
            pre_trigger_delay_mu += self.core.seconds_to_mu(
                self.fast_kinetics_shift_time
            )

        delay_mu(-pre_trigger_delay_mu)

        self.ttl_trigger.pulse_mu(pre_trigger_delay_mu + exposure_mu)

        delay_mu(pre_trigger_delay_mu)

        if control_shutter:
            self.ttl_shutter.off()

    @kernel
    def readout_ROIs(self, sums, means, timeout_mu):
        """
        Read out data from camera

        Must be run at the end of the sequence. Will block until timeout_mu if
        no data was taken, i.e. if the camera was set up incorrectly.

        Will consume all slack and break_realtime.

        Sums and means must be arrays with length = number of ROIs. They will be
        altered with the results.

        Parameters:
        sums (TArray(TInt32)): Array to hold the sum of each ROI
        means (TArray(TFloat)): Array to hold the mean of each ROI
        timeout_mu (int): Timestamp of timeout in machine units
        discard_first_frame (bool): Whether to discard the first frame. This is
            useful when the camera is in fast kinetics mode and the first frame
            is nonsense.
        """

        if len(means) != self.num_rois or len(sums) != self.num_rois:
            raise ValueError("sums and means must be arrays with length num_rois")

        # Get data
        data = [0] * self.num_rois

        # If the andor is in fast kinetics mode and the height of pixels to emit
        # is > 512, it will emit two frames onto Grabber instead of one. The
        # first will be "nonsense" (probably with some digital information that
        # the grabber isn't parsing) and the second will contain all the pixels,
        # up to a max of 1024 high (i.e. the image + storage EMCCDs).
        # See labbook entry 2024-06-11.
        for _ in range(2 if self.andor_requires_storage_frame else 1):
            self.grabber.input_mu(data, timeout_mu=timeout_mu)

        rois = self.andor_camera_config.get_rois()

        for i in range(self.num_rois):
            roi = rois[i]
            area = self.andor_camera_config.calculate_area_from_roi(roi)

            sums[i] = data[i]

            if area == 0:
                means[i] = 0.0
            else:
                means[i] = data[i] / area

    @host_only
    def readout_all_new_images(self, timeout=2.0, num_images=1):
        """
        Reads out all new images from the camera with a specified timeout.

        Parameters:
        timeout (float): The maximum time to wait for images, in seconds. Default is 2.0 seconds.
        num_images (int): The number of images to read out. Default is 1.

        Returns:
            numpy.ndarray: The correctly rotated image as a NumPy array.

        Raises:
            AndorNoImageAvailable if no images were read out
        """

        if self.fast_kinetics_mode:
            self.cam.wait_for_acquisition(timeout=timeout)
        else:
            self.cam.wait_for_new_image(timeout=timeout, num_images=num_images)

        try:
            imgs = self.cam.get_new_images()
        except RuntimeError:
            raise AndorNoImageAvailable("There was no image to read out")

        if imgs.shape[0] != num_images:
            raise ValueError(
                f"Wrong number of images! Shape was {imgs.shape}, expected number of images was {num_images}"
            )

        return np.rot90(imgs, axes=(2, 1))
