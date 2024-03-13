from artiq.coredevice.core import Core
from artiq.experiment import now_mu
from ndscan.experiment import *

from repository.lib.fragments.blue_3d_mot import Blue3DMOTFrag
from repository.lib.fragments.dual_camera_measurer import DualCameraMeasurement


class LoadingSr87(ExpFragment):
    def build_fragment(self) -> None:
        self.setattr_device("core")
        self.core: Core

        self.setattr_fragment("blue_mot", Blue3DMOTFrag)
        self.blue_mot: Blue3DMOTFrag

        self.setattr_fragment(
            "dual_cameras", DualCameraMeasurement, hardware_trigger=True
        )
        self.dual_cameras: DualCameraMeasurement

    @kernel
    def run_once(self) -> None:
        self.core.break_realtime()
        self.blue_mot.load_mot()
        self.dual_cameras.trigger()
        self.core.wait_until_mu(now_mu())
        self.dual_cameras.save_data()
