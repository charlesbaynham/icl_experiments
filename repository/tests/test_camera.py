import logging
import time

import pandas as pd
from artiq.experiment import EnvExperiment
from ndscan.experiment import ExpFragment
from ndscan.experiment.entry_point import make_fragment_scan_exp
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


TestFLIRCameraInterface = make_fragment_scan_exp(TestFLIRCameraInterface)
