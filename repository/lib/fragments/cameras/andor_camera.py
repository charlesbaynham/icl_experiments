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
from artiq.experiment import delay_mu
from artiq.experiment import host_only
from artiq.experiment import kernel
from artiq.experiment import rpc
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


class AndorCameraControl(Fragment):
    """
    Control the Andor camera and associated shutters / triggers

    This Fragment handles triggering and readout (via Grabber). Setup is not yet
    controlled.

    TODO: Add Andor camera parameter control

    By default, this fragment produces 1x ROI with the region set in
    :module:`~.constants`. To override this, pass "roi_defaults" to
    :meth:`~.setattr_fragment`.
    """

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
        add_pre_trigger_delay=True,
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

        # %% Kernel variables
        self.debug_enabled = logger.isEnabledFor(logging.DEBUG)
        self.num_rois = len(roi_defaults)

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
            f"Camera ROI y1",
            default=512,
            min=0,
            max=512,
        )

        self.cam_roi_x0: IntParamHandle
        self.cam_roi_x1: IntParamHandle
        self.cam_roi_y0: IntParamHandle
        self.cam_roi_y1: IntParamHandle

        # %% Kernel invariants
        kernel_invariants = getattr(self, "kernel_invariants", set())
        self.kernel_invariants = kernel_invariants | {
            "debug_enabled",
            "num_rois",
            "ttl_trigger",
            "ttl_shutter",
        }

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
        if self.use_andor_driver.get():
            self.cam: AndorDriver = self.get_device("andor_camera")
            self.set_roi()
            self.cam.setup_shutter("open")
            self.cam.set_trigger_mode("ext_exp")
            # self.cam.set_acquisition_mode("kinetic")
            self.cam.start_acquisition()

        super().host_setup()

    def host_cleanup(self):
        if self.use_andor_driver.get():
            if self.cam.acquisition_in_progress():
                self.cam.stop_acquisition()
            self.cam.setup_shutter("closed")
        super().host_cleanup()

    @host_only
    def set_roi(self):
        roi = {}
        roi["hstart"] = int(self.cam_roi_x0.get())
        roi["hend"] = int(self.cam_roi_x1.get())
        roi["vstart"] = int(self.cam_roi_y0.get())
        roi["vend"] = int(self.cam_roi_y1.get())
        self.cam.set_roi(**roi)

    @kernel
    def device_setup(self) -> None:
        self.device_setup_subfragments()

        # Here we sadly need an RPC. That make this scan a bit slower, but only
        # by a ms or so which is small compared to most (all?) of our sequences
        roi_config = self.calculate_roi_config()

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

        For now, you must manually set up the camera to respond to external
        triggers.

        You should call :meth:`~.save_data` to read out the configured ROI at
        the end of your sequence.

        If control_shutter == True, open the shutter <shutter_delay> in advance
        and then close if afterwards.

        If this Fragment was built with add_pretrigger_delay == True, go back in
        time by <trigger_delay> then trigger the camera for <trigger_delay> +
        <exposure>. Otherwise, just expose the camera for <exposure>.

        Advances the timeline by the duration of the camera's exposure
        """

        if control_shutter:
            shutter_delay_mu = self.core.seconds_to_mu(self.shutter_delay.get())
            delay_mu(-shutter_delay_mu)
            self.ttl_shutter.on()
            delay_mu(shutter_delay_mu)

        pre_trigger_delay_mu = self.core.seconds_to_mu(self.pre_trigger_delay.get())
        exposure_mu = self.core.seconds_to_mu(exposure)

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
        """

        if len(means) != self.num_rois or len(sums) != self.num_rois:
            raise ValueError("sums and means must be arrays with length num_rois")

        # Get data
        data = [0] * self.num_rois
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
    def readout_image(self, timeout=2.0):
        self.cam.wait_for_frame(timeout=timeout, since="lastread")
        img = self.cam.read_oldest_image()
        img_array = np.array(img)
        img_array = np.rot90(img_array, axes=(1, 0))
        return img_array

    @host_only
    def readout_n_images(self, n_frames, timeout=2.0):
        self.cam.wait_for_frame(nframes=n_frames, timeout=timeout, since="lastread")
        imgs = self.cam.read_multiple_images()
        for i, img in enumerate(imgs):
            imgs[i] = np.rot90(np.array(img), axes=(1, 0))
        return imgs

    @host_only
    def slice_image(self, img):
        sum_slice_x = np.sum(img, axis=1)
        sum_slice_y = np.sum(img, axis=0)
        return sum_slice_x, sum_slice_y
