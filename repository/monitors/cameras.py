from ndscan.experiment.entry_point import make_fragment_scan_exp

from repository.lib.fragments.cameras.flir_camera import Chamber2HorizontalCamera
from repository.lib.fragments.cameras.flir_camera import Chamber2VerticalCamera
from repository.lib.fragments.cameras.flir_camera import MonitorCameraExp


class MonitorChamber2HorizCamera(MonitorCameraExp):
    def build_fragment(self):
        self.set_default_scheduling(pipeline_name="cam_h")
        super().build_fragment()

    camera_class = Chamber2HorizontalCamera


class MonitorChamber2VertCamera(MonitorCameraExp):
    def build_fragment(self):
        self.set_default_scheduling(pipeline_name="cam_v")
        super().build_fragment()

    camera_class = Chamber2VerticalCamera


MonitorChamber2HorizCamera = make_fragment_scan_exp(MonitorChamber2HorizCamera)  # type: ignore
MonitorChamber2VertCamera = make_fragment_scan_exp(MonitorChamber2VertCamera)  # type: ignore
