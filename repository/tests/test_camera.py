import logging
import time

import pandas as pd
from artiq.coredevice.core import Core
from artiq.experiment import delay
from artiq.experiment import EnvExperiment
from artiq.experiment import kernel
from artiq.experiment import now_mu
from artiq.experiment import rpc
from ndscan.experiment import ExpFragment
from ndscan.experiment.entry_point import make_fragment_scan_exp
from ndscan.experiment.result_channels import OpaqueChannel
from pyaion.fragments.suservo import LibSetSUServoStatic
from retry import retry

from repository.lib.fragments.flir_camera import Chamber2Camera


class TestFLIRCamera(EnvExperiment):
    def run(self):
        # This import happens here because, for some reason, importing the
        # gi.repository Aravis (which happens in python-aravis) breaks if you do
        # it from multiple processes at the same time, which ARTIQ will trigger
        # when scanning for experiments
        from aravis import Camera

        cam = Camera("FLIR-Blackfly S BFS-PGE-50S5M-22018873", loglevel=logging.INFO)
        cam.start_acquisition_trigger()

        cam.trigger()

        frame = self.get_frame(cam)

        print(frame)

    @retry(delay=1e-3, tries=1000)
    def get_frame(self, cam):
        f = cam.try_pop_frame()
        if f is None:
            raise RuntimeError
        return f


class TestFLIRCameraInterface(ExpFragment):
    def build_fragment(self):
        self.setattr_fragment("cam", Chamber2Camera)
        self.cam: Chamber2Camera

    def host_setup(self):
        super().host_setup()

        self.cam.ready_for_trigger(exposure_us=1000, num_images=3)

        for _ in range(3):
            self.cam.trigger()
            time.sleep(0.1)

        frames = self.cam.get_frames()

        print(f"Got {len(frames)} frames:")

        for ts, frame in frames:
            print(pd.Timedelta(ts, "ns"))
            print(frame)


class TestFLIRAgainstLightBG(ExpFragment):
    def build_fragment(self):
        self.setattr_device("core")
        self.core: Core

        self.setattr_fragment("cam", Chamber2Camera)
        self.cam: Chamber2Camera

        self.setattr_fragment(
            "suservo_setter",
            LibSetSUServoStatic,
            "suservo_aom_singlepass_461_3DMOT_axialplus",
        )
        self.suservo_setter: LibSetSUServoStatic

        self.setattr_result("images", OpaqueChannel)
        self.images: OpaqueChannel

        self.image_list = []

    @rpc
    def setup_camera(self):
        self.cam.ready_for_trigger(exposure_us=1000, num_images=1)

    @rpc
    def get_frame(self):
        self.cam.trigger()
        self.image_list.append(self.cam.get_one_frame())

    @kernel
    def run_once(self):
        amplitudes = [0.0, 0.2, 0.4, 0.6, 0.8, 1.0]

        for amplitude in amplitudes:
            self.setup_camera()

            self.core.break_realtime()
            self.suservo_setter.set_suservo(
                150e6, amplitude=amplitude, attenuation=20.0
            )

            delay(250e-3)
            self.core.wait_until_mu(now_mu())

            self.get_frame()

            delay(100e-3)

            self.push()

    @rpc
    def push(self):
        self.images.push(self.image_list)


TestFLIRCameraInterface = make_fragment_scan_exp(TestFLIRCameraInterface)

TestFLIRAgainstLightBG = make_fragment_scan_exp(TestFLIRAgainstLightBG)
