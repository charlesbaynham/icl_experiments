import abc
import logging

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

    num_andor_images = None
    "How many images will the Andor driver read out"
    num_images_per_series = None
    "How many images will the Andor driver read out in each series"
    num_grabber_rois = None
    "How many ROIs in each image for the Grabber"
    num_grabber_readouts = None
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

    @portable
    @abc.abstractmethod
    def get_rois(self) -> TArray(TInt32, 2):  # pyright: ignore[reportInvalidTypeForm]
        """
        Get the list of desired grabber ROIs

        Returns an array of size (N, 4) where each line is (x0, y0, x1, y1)
        """


class AndorCameraDefaultConfig(AndorCameraConfig):
    def build_fragment(self, roi_defaults=None):

        if roi_defaults is None:
            self.roi = [
                [
                    constants.ANDOR_ROI_X0,
                    constants.ANDOR_ROI_Y0,
                    constants.ANDOR_ROI_X1,
                    constants.ANDOR_ROI_Y1,
                ]
            ]
        else:
            self.roi = roi_defaults

        self.num_rois = len(self.roi)

    def overwrite_all_rois(self, rois):
        """
        Overwrite all the ROIs at once from a list of ROIs.

        Parameters:
        rois (List[List[int, int, int, int]]): List of ROIs
        """

        self.rois = rois
        self.num_rois = len(rois)

    def update_roi_i(self, i, new_roi):
        """
        Update a single ROI from a new ROI, the new ROI must have the same shape as the old ROI

        Parameters:
        i (int): Index of the ROI to update
        new_roi (List[int, int, int, int]): New ROI
        """

        for j in range(4):
            self.rois[i][j] += new_roi[j]

    def update_all_rois(self, new_rois):
        """
        Update all the ROIs at once from a list of ROIs, the new rois must have the same shape as the old rois

        Parameters:
        rois (List[List[int, int, int, int]]): List of ROIs
        """

        for i in range(self.num_rois):
            # Should I manually expand this? Does it make it faster?
            self.update_roi_i(i, new_rois[i])

    def update_vertical_rois(self, i, delta_ys):
        """
        This is a special implementation of update_roi_i that just updates the y values

        Parameters:
        i (int): Index of the ROI to update
        delta_ys (List[int, int]): List of changes to y0 and y1
        """

        self.rois[i][1] += delta_ys[0]
        self.rois[i][3] += delta_ys[1]

    def get_rois(self):
        """
        A simple function to get the ROIs
        """

        return self.rois

    @rpc
    def calculate_roi_config(self) -> TArray(TInt32, 2):
        """
        Populate an ROI array from the generated NDScan parameters

        This unfortunately has to happen on the host since it uses various
        python features that aren't available in kernels
        """

        rois = np.zeros((self.num_rois, 4), dtype=int)
        for i in range(self.num_rois):
            param_prefix = f"roi_{i}_"
            rois[i, :] = [
                getattr(self, param_prefix + "x0").get(),
                getattr(self, param_prefix + "y0").get(),
                getattr(self, param_prefix + "x1").get(),
                getattr(self, param_prefix + "y1").get(),
            ]

        return rois


class AndorCameraControl(Fragment):
    """
    Control the Andor camera and associated shutters / triggers

    This Fragment handles triggering and readout (via Grabber). Setup is not yet
    controlled.

    TODO: Add Andor camera parameter control

    By default, this fragment produces 1x ROI with the region set in
    :module:`~.constants`. To override this, pass "roi_defaults" to
    :meth:`~.setattr_fragment`.

    Parameters:
    roi_defaults (List[List[int, int, int, int]]): List of ROIs to set up
    add_pre_trigger_delay (bool): Whether to add a delay before triggering the
        camera.
    fast_kinetics_num_shots (int): Number of shots to per frame. If > 1,
        fast kinetics mode will be used.
    """

    keep_andor_shutter_closed = False  # HACK this is ugly

    def build_fragment(
        self,
        roi_defaults=[
            [
                constants.ANDOR_ROI_X0,
                constants.ANDOR_ROI_Y0,
                constants.ANDOR_ROI_X1,
                constants.ANDOR_ROI_Y1,
            ]
        ],
        fast_kinetics_height_default=None,
        fast_kinetics_offset_default=None,
        add_pre_trigger_delay=True,
        fast_kinetics_num_shots=1,
    ):
        self.setattr_device("core")
        self.core: Core

        self.setattr_device("grabber0")
        self.grabber: Grabber = self.grabber0

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

        for i, (x0, y0, x1, y1) in enumerate(roi_defaults):
            self.setattr_param(
                f"roi_{i}_x0",
                IntParam,
                f"Grabber ROI {i} x0",
                default=x0,
                min=0,
                max=512,
            )
            self.setattr_param(
                f"roi_{i}_x1",
                IntParam,
                f"Grabber ROI {i} x1",
                default=x1,
                min=0,
                max=512,
            )
            self.setattr_param(
                f"roi_{i}_y0",
                IntParam,
                f"Grabber ROI {i} y0",
                default=y0,
                min=0,
                max=1024,
            )
            self.setattr_param(
                f"roi_{i}_y1",
                IntParam,
                f"Grabber ROI {i} y1",
                default=y1,
                min=0,
                max=1024,
            )

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

        self.fast_kinetics_mode = fast_kinetics_num_shots > 1

        if self.fast_kinetics_mode:
            self.setattr_param(
                "fast_kinetics_height",
                IntParam,
                "Fast kinetics height",
                default=fast_kinetics_height_default,
                min=0,
                max=512,
            )
            self.setattr_param(
                "fast_kinetics_time_between_shots",
                FloatParam,
                "Fast kinetics time between shots",
                default=1e-6,
                unit="us",
                min=0,
            )
            # Note that fast_kinetics_time_between_shots is not equal to the
            # "exposure time" described in the Andor manual!
            # fast_kinetics_time_between_shots == exposure time +
            # fast_kinetics_shift_time

            self.setattr_param(
                "fast_kinetics_offset",
                IntParam,
                "Fast kinetics offset",
                default=fast_kinetics_offset_default,
                min=0,
                max=512,
            )

        self.cam_roi_x0: IntParamHandle
        self.cam_roi_x1: IntParamHandle
        self.cam_roi_y0: IntParamHandle
        self.cam_roi_y1: IntParamHandle
        self.fast_kinetics_height: IntParamHandle
        self.fast_kinetics_time_between_shots: FloatParamHandle
        self.fast_kinetics_offset: IntParamHandle

        # %% Kernel variables

        self.fast_kinetics_num_shots = fast_kinetics_num_shots

        self.debug_enabled = logger.isEnabledFor(logging.DEBUG)
        self.num_rois = len(roi_defaults)

        self.kernel_invariants = getattr(self, "kernel_invariants", set())
        self.kernel_invariants.add("debug_enabled")
        self.kernel_invariants.add("fast_kinetics_mode")
        self.kernel_invariants.add("fast_kinetics_num_shots")
        self.kernel_invariants.add("andor_requires_storage_frame")
        self.kernel_invariants.add("num_rois")
        self.kernel_invariants.add("ttl_trigger")
        self.kernel_invariants.add("ttl_shutter")

    @rpc
    def calculate_roi_config(self) -> TArray(TInt32, 2):
        """
        Populate an ROI array from the generated NDScan parameters

        This unfortunately has to happen on the host since it uses various
        python features that aren't available in kernels
        """

        rois = np.zeros((self.num_rois, 4), dtype=int)
        for i in range(self.num_rois):
            param_prefix = f"roi_{i}_"
            rois[i, :] = [
                getattr(self, param_prefix + "x0").get(),
                getattr(self, param_prefix + "y0").get(),
                getattr(self, param_prefix + "x1").get(),
                getattr(self, param_prefix + "y1").get(),
            ]

        return rois

    def host_setup(self):
        self.fast_kinetics_shift_time = 0.0  # to prevent compilation errors
        # If the andor is in fast kinetics mode and the height of pixels to emit
        # is > 512, it will emit two frames onto Grabber instead of one. The
        # first will be "nonsense" (probably with some digital information that
        # the grabber isn't parsing) and the second will contain all the pixels,
        # up to a max of 1024 high (i.e. the image + storage EMCCDs).
        # See labbook entry 2024-06-11.
        self.andor_requires_storage_frame = self.fast_kinetics_mode and (
            self.fast_kinetics_height.get() * self.fast_kinetics_num_shots
            > constants.ANDOR_SENSOR_HEIGHT
        )

        if self.use_andor_driver.get():
            self.cam: AndorDriver = self.get_device("andor_camera")
            if self.cam.get_status() == 20072:
                logger.warning("Andor still acquiring, stopping acquisition")
                self.cam.stop_acquisition()
            self.set_roi()
            self.cam.set_baseline_clamp(self.baseline_clamp_mode.get())
            if not self.keep_andor_shutter_closed:
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
                    self.fast_kinetics_height.get() * self.cam.get_vsspeed() * 1e-6
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
    def setup_fast_kinetics_mode(self):
        exposure_time = (
            self.fast_kinetics_time_between_shots.get() - self.fast_kinetics_shift_time
        )

        if exposure_time < 0:
            raise ValueError(
                "fast_kinetics_time_between_shots must be greater than the time required"
                f" to shift out one Fast Kinetics region = {1e6*self.fast_kinetics_shift_time:.3f} us"
            )
        self.cam.stop_acquisition()
        self.cam.setup_fast_kinetics_mode(
            num_acc=self.fast_kinetics_num_shots,
            subarea_height=self.fast_kinetics_height.get(),
            exposure_time=exposure_time,
            offset=self.fast_kinetics_offset.get(),
        )

    @kernel
    def device_setup(self) -> None:
        self.device_setup_subfragments()

        # Here we sadly need an RPC. That make this scan a bit slower, but only
        # by a ms or so which is small compared to most (all?) of our sequences.
        # TODO: detect if ROI is not scanned and only run this once in that case.
        roi_config = self.calculate_roi_config()

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

        for i in range(self.num_rois):
            self.core.break_realtime()
            self.grabber.setup_roi(
                i,
                roi_config[i, 0],
                roi_config[i, 1],
                roi_config[i, 2],
                roi_config[i, 3],
            )
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
    def set_shutter(self, state: TBool):
        """
        Open or close the protective shutter

        This will be automatically closed at the end of a sequence if you
        forget, but you should close it immediately after use to avoid damaging
        the camera with lots of light while it's in EM gain mode.
        """
        self.ttl_shutter.set_o(state)

    @kernel
    def trigger(self, exposure: TFloat, control_shutter=False):
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

    @host_only
    def slice_from_roi_params(self, img, i, prefix="roi_", obj=None):
        x0, y0, x1, y1 = self.get_roi_i(i, prefix=prefix, obj=obj)
        width, height = img.shape

        logger.debug(f"Image shape: {width}, {height}")
        logger.debug(f"ROI: {x0}, {x1}, {y0}, {y1}")

        return img[x0:x1, height - y0 : height - y1 : -1], (x0, y0)

    @host_only
    def get_roi_i(self, i, prefix="roi_", obj=None):
        if obj is None:
            obj = self
        x0 = getattr(obj, f"{prefix}{i}_x0").get()
        y0 = getattr(obj, f"{prefix}{i}_y0").get()
        x1 = getattr(obj, f"{prefix}{i}_x1").get()
        y1 = getattr(obj, f"{prefix}{i}_y1").get()
        return [x0, y0, x1, y1]

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

        # TODO: assumes all ROIs have same area
        area = (self.roi_0_x1.get() - self.roi_0_x0.get()) * (
            self.roi_0_y1.get() - self.roi_0_y0.get()
        )

        for i in range(self.num_rois):
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

    ###
    # This this wasn't working, and I haven't figured out why yet.
    # For now, calling readout_image() n times does what
    # readout_n_images(n) once should do anyway
    # TODO: make it work
    ###
    # @host_only
    # def readout_n_images(self, n_frames, timeout=2.0):
    #     self.cam.wait_for_frame(nframes=n_frames, timeout=timeout, since="lastread")

    #     for i, img in enumerate(imgs):
    #         imgs[i] = np.rot90(np.array(img), axes=(1, 0))
    #     return imgs
