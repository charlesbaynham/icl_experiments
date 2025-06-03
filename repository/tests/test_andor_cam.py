import logging
from typing import List

import numpy as np
from andor_artiq_ndsp.driver import AndorDriver
from artiq.coredevice.core import Core
from artiq.coredevice.grabber import Grabber
from artiq.coredevice.ttl import TTLOut
from artiq.experiment import TBool
from artiq.language import delay
from artiq.language import delay_mu
from artiq.language import host_only
from artiq.language import kernel
from artiq.language import rpc
from ndscan.experiment import ExpFragment
from ndscan.experiment import make_fragment_scan_exp
from ndscan.experiment.parameters import BoolParam
from ndscan.experiment.parameters import BoolParamHandle
from ndscan.experiment.parameters import FloatParam
from ndscan.experiment.parameters import FloatParamHandle
from ndscan.experiment.parameters import IntParam
from ndscan.experiment.parameters import IntParamHandle
from ndscan.experiment.result_channels import FloatChannel
from ndscan.experiment.result_channels import OpaqueChannel
from numpy import int64

from repository.lib import constants

logger = logging.getLogger(__name__)


class TestAndorCamFrag(ExpFragment):
    def build_fragment(self) -> None:
        roi_defaults = [
            constants.ANDOR_ROI_X0,
            constants.ANDOR_ROI_Y0,
            constants.ANDOR_ROI_X1,
            constants.ANDOR_ROI_Y1,
        ]

        self.setattr_param(
            "rpc_snap", BoolParam, description="snap with rpc", default=True
        )
        self.rpc_snap: BoolParamHandle

        self.setattr_param(
            "fast_kinetics", BoolParam, description="fast kinetics mode", default=True
        )
        self.fast_kinetics: BoolParamHandle

        self.setattr_param(
            "n_frames",
            IntParam,
            "n frames",
            default=1,
            min=1,
        )
        self.n_frames: IntParamHandle

        self.setattr_param(
            "frame_delay",
            FloatParam,
            "frame delay",
            default=10e-6,
            min=1e-6,
            max=1,
        )
        self.frame_delay: FloatParamHandle

        self.setattr_param(
            "timeout",
            FloatParam,
            "timout",
            default=1,
            min=1e-6,
            max=100,
        )
        self.timeout: FloatParamHandle

        self.setattr_param(
            "exposure_time",
            FloatParam,
            "exposure_time",
            default=10e-6,
            min=1e-6,
            max=100e-6,
        )
        self.exposure_time: FloatParamHandle

        self.setattr_param(
            "roi_x0",
            IntParam,
            "ROI x0",
            default=roi_defaults[0],
            min=0,
            max=512,
        )

        self.roi_x0: IntParamHandle

        self.setattr_param(
            "roi_y0",
            IntParam,
            "ROI y0",
            default=roi_defaults[1],
            min=0,
            max=512,
        )
        self.roi_y0: IntParamHandle

        self.setattr_param(
            "roi_x1",
            IntParam,
            "ROI x1",
            default=roi_defaults[2],
            min=0,
            max=512,
        )
        self.roi_x1: IntParamHandle

        self.setattr_param(
            "roi_y1",
            IntParam,
            "ROI y1",
            default=roi_defaults[3],
            min=0,
            max=512,
        )
        self.roi_y1: IntParamHandle

        self.setattr_param(
            "pre_trigger_delay",
            FloatParam,
            "Time to allow for camera triggering to be enabled",
            default=constants.ANDOR_CAMERA_TRIGGER_ENABLE_TIME,
            unit="us",
            min=0.0,
        )
        self.pre_trigger_delay: FloatParamHandle

        self.setattr_param(
            "shutter_delay",
            FloatParam,
            "Time to allow for shutter to open before imaging",
            default=constants.ANDOR_CAMERA_SHUTTER_OPEN_TIME,
            unit="ms",
            min=0.0,
        )
        self.shutter_delay: FloatParamHandle

        self.img_channels: List[OpaqueChannel] = []
        self.sum_channels: List[FloatChannel] = []
        self.mean_channels: List[OpaqueChannel] = []

        self.setattr_param(
            "one_applet", BoolParam, description="only one applet", default=True
        )
        self.one_applet: BoolParamHandle

        for i in range(4):
            img_ch = self.setattr_result(f"andor_image_{i}", OpaqueChannel)
            self.img_channels.append(img_ch)
            sum_ch = self.setattr_result(f"andor_sum_{i}", FloatChannel)
            self.sum_channels.append(sum_ch)
            mean_ch = self.setattr_result(f"andor_mean_{i}", FloatChannel)
            self.mean_channels.append(mean_ch)

        self.setattr_device("core")
        self.core: Core

        self.setattr_device("grabber0")
        self.grabber: Grabber = self.grabber0

        self.ttl_trigger: TTLOut = self.get_device("ttl_camera_trigger_andor")
        self.ttl_shutter: TTLOut = self.get_device("ttl_shutter_andor")
        self.cam = self.get_device("andor_camera")
        self.cam: AndorDriver

        self.setattr_device("ccb")

    def host_setup(self):
        self.print_info()
        self.set_roi()
        # Setup shutter
        self.cam.setup_shutter("open")
        # self.cam.setup_cont_mode()
        if self.fast_kinetics.get():
            logger.debug("made it to setting up fk mode")
            self.cam.set_trigger_mode("ext")
            self.cam.setup_fast_kinetic_mode(num_acc=self.n_frames.get())
            # self.cam.set_acquisition_mode("fast_kinetic", setup_params=True)
            self.cam.start_acquisition()

        elif self.rpc_snap.get():
            self.cam.set_trigger_mode("int")
            self.cam.set_exposure(self.exposure_time.get())
        else:
            self.cam.set_trigger_mode("ext_exp")
            # self.cam.set_acquisition_mode("kinetic")
            self.cam.start_acquisition()

        # Launch monitors
        # Always launch these even if we're not saving raw data - we'll write zeros if not

        if self.one_applet.get():
            frames = 1
        else:
            frames = self.n_frames.get()
            for i in range(frames):
                self.set_dataset(
                    f"andor_image_{i}",
                    np.array([[0.0]]),
                    broadcast=True,
                    persist=False,
                    archive=False,
                )

                self.ccb.issue(
                    "create_applet",
                    f"Andor image {i}",
                    f"${{artiq_applet}}image {f'andor_image_{i}'}",
                )

        super().host_setup()

    @kernel
    def device_setup(self) -> None:
        self.device_setup_subfragments()

        # self.set_exposure()

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

    def host_cleanup(self):
        if self.cam.acquisition_in_progress():
            self.cam.stop_acquisition()
        self.cam.setup_shutter("closed")

    @kernel
    def device_cleanup(self) -> None:
        self.device_cleanup_subfragments()

        # Ensure the camera's protective shutter is closed
        self.core.break_realtime()
        self.ttl_shutter.off()

    @rpc
    def set_roi(self):
        roi = {}
        roi["hstart"] = int(self.roi_x0.get())
        roi["hend"] = int(self.roi_x1.get())
        roi["vstart"] = int(self.roi_y0.get())
        roi["vend"] = int(self.roi_y1.get())
        self.cam.set_roi(**roi)

    @rpc
    def set_exposure(self):
        self.cam.set_exposure(self.exposure_time.get())

    @kernel
    def set_shutter(self, state: TBool):
        """
        Open or close the protective shutter

        This will be automatically closed at the end of a sequence if you
        forget, but you should close it immediately after use to avoid damaging
        the camera with lots of light while it's in EM gain mode.
        """
        self.ttl_shutter.set_o(state)

    # @kernel
    # def trigger(self, exposure: TFloat, control_shutter=False):
    #     """
    #     Trigger an aquisition

    #     For now, you must manually set up the camera to respond to external
    #     triggers.

    #     You should call :meth:`~.save_data` to read out the configured ROI at
    #     the end of your sequence.

    #     If control_shutter == True, open the shutter <shutter_delay> in advance
    #     and then close if afterwards.

    #     If this Fragment was built with add_pretrigger_delay == True, go back in
    #     time by <trigger_delay> then trigger the camera for <trigger_delay> +
    #     <exposure>. Otherwise, just expose the camera for <exposure>.

    #     Advances the timeline by the duration of the camera's exposure
    #     """

    #     if control_shutter:
    #         shutter_delay_mu = self.core.seconds_to_mu(self.shutter_delay.get())
    #         delay_mu(-shutter_delay_mu)
    #         self.ttl_shutter.on()
    #         delay_mu(shutter_delay_mu)

    #     pre_trigger_delay_mu = self.core.seconds_to_mu(self.pre_trigger_delay.get())
    #     exposure_mu = self.core.seconds_to_mu(exposure)

    #     delay_mu(-pre_trigger_delay_mu)

    #     self.ttl_trigger.pulse_mu(pre_trigger_delay_mu + exposure_mu)

    #     delay_mu(pre_trigger_delay_mu)

    #     if control_shutter:
    #         self.ttl_shutter.off()

    @kernel
    def trigger(self):
        self.core.break_realtime()
        self.ttl_trigger.pulse(self.exposure_time.get())

    @kernel
    def run_once(self) -> None:
        self.core.break_realtime()
        if self.rpc_snap.get():
            self.take_image_rpc()
        else:
            self.core.break_realtime()
            if self.fast_kinetics.get():
                n_frames = 1
            else:
                n_frames = self.n_frames.get()
            for _ in range(n_frames):
                self.trigger()
                delay(self.frame_delay.get())
            self.read_images()

    def print_info(self):
        info = self.cam.get_device_info(asdict=True)
        # logger.info("Device info: {}".format(info.serial_number))
        print("Device info: {}".format(info))

        temp = self.cam.get_temperature()
        # logger.info("Temperature: {}".format(temp))
        print("Temperature: {}".format(temp))

        amp_mode = self.cam.get_amp_mode(asdict=True)
        # logger.info("Amp mode: {}".format(amp_mode.preamp))
        print("Amp mode: {}".format(amp_mode))

        eem_gain = self.cam.get_EMCCD_gain()
        print("EM gain: {}".format(eem_gain))

    @rpc
    def take_image_rpc(self):
        n_frames = self.n_frames.get()
        imgs = self.cam.grab(nframes=n_frames)
        for i in range(n_frames):
            self.analyse_data(i, imgs[i])

    @host_only
    def analyse_data(self, i, img):
        img_array = np.array(img)
        img_mean = np.mean(img_array.flat)
        img_sum = np.sum(img_array.flat)
        self.set_dataset(
            f"andor_image_{i}",
            img_array,
            broadcast=True,
            persist=False,
            archive=False,
        )
        self.mean_channels[i].push(img_mean)
        self.sum_channels[i].push(img_sum)

    @rpc(flags={"async"})
    def read_images(self):
        if self.fast_kinetics.get():
            n_frames = 1
        else:
            n_frames = self.n_frames.get()
        self.cam.wait_for_frame(
            nframes=n_frames, timeout=self.timeout.get(), since="lastread"
        )
        # for i in range(n_frames):
        #     img = self.cam.read_newest_image()
        #     logger.info("img: {}".format(img))
        #     if img is not None:
        #         self.analyse_data(i, img)
        #     else:
        #         logger.info("no image")
        #         self.analyse_data(i, [[1.0, 0.0], [0.0, 1.0]])

        imgs = self.cam.read_multiple_images()
        logger.info(f"number of images received: {len(imgs)}")
        if self.one_applet.get():
            self.analyse_data(0, imgs[0])
        else:
            for i, img in enumerate(imgs):
                if img is not None:
                    self.analyse_data(i, img)
                else:
                    logger.info("no image")
                    self.analyse_data(i, [[1.0, 0.0], [0.0, 1.0]])


TestAndorCam = make_fragment_scan_exp(TestAndorCamFrag)
