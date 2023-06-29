import logging

import numpy as np
from artiq.coredevice.core import Core
from artiq.experiment import delay
from artiq.experiment import kernel
from artiq.experiment import ms
from artiq.experiment import now_mu
from artiq.experiment import rpc
from ndscan.experiment import ExpFragment
from ndscan.experiment import ResultChannel
from ndscan.experiment.entry_point import make_fragment_scan_exp
from ndscan.experiment.parameters import FloatParam
from ndscan.experiment.parameters import FloatParamHandle
from ndscan.experiment.result_channels import FloatChannel
from ndscan.experiment.result_channels import IntChannel
from ndscan.experiment.result_channels import OpaqueChannel

from repository.lib.fragments.blue_3d_mot import Blue3DMOTFrag
from repository.lib.fragments.chamber_photodiode import MOTPhotodiodeMeasurement
from repository.lib.fragments.dual_camera_measurer import BGCorrectedMeasurement


logger = logging.getLogger(__name__)


class MeasureBlueMOTFrag(ExpFragment):
    def build_fragment(self):
        self.setattr_device("core")
        self.core: Core

        self.setattr_fragment("mot_controller", Blue3DMOTFrag)
        self.mot_controller: Blue3DMOTFrag

        self.setattr_param_rebind(
            "mot_loading_time", self.mot_controller, "loading_time"
        )
        self.mot_loading_time: FloatParamHandle

        self.setattr_param(
            "delay_between_points",
            FloatParam,
            "Delay between measurements",
            default=0,
            min=0,
            unit="s",
        )
        self.delay_between_points: FloatParamHandle

    @kernel
    def _take_data(self, loading_time):
        raise NotImplementedError

    @kernel
    def run_once(self):
        self.core.break_realtime()

        self.mot_controller.init()
        self.mot_controller.enable_mot_fields()
        self.mot_controller.clear_ch2()

        self._before_start_load_hook()

        # Load MOT and start measuring signal immediately
        self.mot_controller.turn_on_3d_and_2d_beams()

        self._take_data(self.mot_loading_time.get())

        delay(self.delay_between_points.get())
        self.core.wait_until_mu(now_mu())

    @kernel
    def _before_start_load_hook(self):
        pass


class MeasureBlueMOTWithPDFrag(MeasureBlueMOTFrag):
    def build_fragment(self):
        self.setattr_param(
            "delay_between_trace_points",
            FloatParam,
            description="Delay between points in the photodiode trace",
            default=1 * ms,
            unit="ms",
            min=1 * ms,
            step=1,
        )
        self.delay_between_trace_points: FloatParamHandle

        self.setattr_fragment("mot_measurer_pd", MOTPhotodiodeMeasurement)
        self.mot_measurer_pd: MOTPhotodiodeMeasurement

        self.setattr_result("photodiode_voltage", OpaqueChannel)
        self.photodiode_voltage: ResultChannel

        self.setattr_result("photodiode_mean_voltage", FloatChannel)
        self.photodiode_mean_voltage: ResultChannel

        super().build_fragment()

    @kernel
    def _take_data(self, loading_time):
        num_points = int(loading_time / self.delay_between_trace_points.get())

        trace_data = [0.0] * num_points

        self.mot_measurer_pd.measure_MOT_fluorescence(
            num_points=num_points,
            delay_between_points_mu=self.core.seconds_to_mu(
                self.delay_between_trace_points.get()
            ),
            data=trace_data,
        )

        self.photodiode_voltage.push(np.array(trace_data))
        mean_voltage = 0.0
        for i in range(len(trace_data)):
            mean_voltage += trace_data[i]
        mean_voltage /= len(trace_data)
        self.photodiode_mean_voltage.push(mean_voltage)


class MeasureBlueMOTWithCameraFrag(MeasureBlueMOTFrag):
    def build_fragment(self):
        self.setattr_param(
            "exposure_horiz",
            FloatParam,
            description="Image exposure horizontal",
            default=1e-3,
            min=0,
            unit="us",
            step=1,
        )
        self.exposure_horiz: FloatParamHandle

        self.setattr_param(
            "exposure_vert",
            FloatParam,
            description="Image exposure vertical",
            default=1e-3,
            min=0,
            unit="us",
            step=1,
        )
        self.exposure_vert: FloatParamHandle

        self.setattr_fragment("camera_bg_corrected", BGCorrectedMeasurement)
        self.camera_bg_corrected: BGCorrectedMeasurement

        super().build_fragment()

    @kernel
    def _before_start_load_hook(self):
        """
        Before the MOT is loaded, take a background picture
        """
        delay(-50e-3)

        # Turn on just the 3d beams for a background picture
        self.mot_controller.turn_on_3d_beams()

        self.core.wait_until_mu(now_mu())
        self.camera_bg_corrected.trigger_background()

        delay(50e-3)

    @kernel
    def _take_data(self, loading_time):

        delay(loading_time)

        self.core.wait_until_mu(now_mu())

        self.camera_bg_corrected.trigger_signal()

        self.camera_bg_corrected.save_data()


MeasureBlueMOTWithPD = make_fragment_scan_exp(MeasureBlueMOTWithPDFrag)
MeasureBlueMOTWithCamera = make_fragment_scan_exp(MeasureBlueMOTWithCameraFrag)
