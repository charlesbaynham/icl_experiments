import logging

import numpy as np
from artiq.coredevice.core import Core
from artiq.coredevice.ttl import TTLOut
from artiq.experiment import delay
from artiq.experiment import kernel
from artiq.experiment import ms
from artiq.experiment import now_mu
from artiq.experiment import ns
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
from repository.lib.fragments.blue_3d_mot import MOTPhotodiodeMeasurement
from repository.lib.fragments.flir_camera import Chamber2HorizontalCamera
from repository.lib.fragments.flir_camera import Chamber2VerticalCamera


logger = logging.getLogger(__name__)


class MeasureMOTFrag(ExpFragment):
    def build_fragment(self):
        self.setattr_device("core")
        self.core: Core

        self.setattr_fragment("mot_controller", Blue3DMOTFrag)
        self.mot_controller: Blue3DMOTFrag

        # The repumpers are not yet driven by ARTIQ, but we do have access to their shutters
        self.repumper_707_shutter: TTLOut = self.get_device(
            "TTL_shutter_707_temporary_shutter"
        )
        self.repumper_679_shutter: TTLOut = self.get_device(
            "TTL_shutter_679_temporary_shutter"
        )

        self.setattr_param(
            "mot_loading_time",
            FloatParam,
            description="Time to wait for the 3D MOT to load",
            default=100 * ms,
            min=0,
            unit="ms",
            step=1,
        )
        self.mot_loading_time: FloatParamHandle

    @kernel
    def _take_data(self, loading_time):
        raise NotImplementedError

    @kernel
    def run_once(self):
        self.core.break_realtime()

        delay(10e-6)
        # Turn on the 2D/3D beams & AOMs,
        # but block the important ones, leaving the repumpers on
        self.mot_controller.enable_mot_defaults()
        delay(20 * ns)
        self.repumper_707_shutter.on()
        self.repumper_679_shutter.on()
        delay(1 * ms)
        self.mot_controller.turn_off_3d_and_2d_beams()

        delay(
            100 * ms
        )  # Wait to allow atoms to disperse if there were any hanging around

        self._before_start_load_hook()

        # Load MOT and start measuring signal immediately
        self.mot_controller.turn_on_3d_and_2d_beams()

        self._take_data(self.mot_loading_time.get())

    @kernel
    def _before_start_load_hook(self):
        pass


class MeasureMotWithPDFrag(MeasureMOTFrag):
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


class MeasureMotWithCameraFrag(MeasureMOTFrag):
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

        self.setattr_fragment(
            "mot_measurer_camera_horizontal", Chamber2HorizontalCamera
        )
        self.mot_measurer_camera_horizontal: Chamber2HorizontalCamera

        self.setattr_fragment("mot_measurer_camera_vertical", Chamber2VerticalCamera)
        self.mot_measurer_camera_vertical: Chamber2VerticalCamera

        self.setattr_result("image_horizontal", OpaqueChannel)
        self.image_horizontal: ResultChannel

        self.setattr_result(
            "image_horizontal_timestamp", IntChannel, display_hints={"priority": -1}
        )
        self.image_horizontal_timestamp: ResultChannel

        self.setattr_result("image_horizontal_mean", FloatChannel)
        self.image_horizontal_mean: ResultChannel

        self.setattr_result("image_vertical", OpaqueChannel)
        self.image_vertical: ResultChannel

        self.setattr_result(
            "image_vertical_timestamp", IntChannel, display_hints={"priority": -1}
        )
        self.image_vertical_timestamp: ResultChannel

        self.setattr_result("image_vertical_mean", FloatChannel)
        self.image_vertical_mean: ResultChannel

        self.setup_happened = False

        super().build_fragment()

    @kernel
    def device_setup(self) -> None:
        self.device_setup_subfragments()

        self.core.break_realtime()

        # Prepare cameras to be triggered for 2x acquisitions
        if not self.setup_happened:
            self.mot_measurer_camera_horizontal.ready_for_trigger(
                self.exposure_horiz.get() * 1e6, num_images=2
            )
            self.mot_measurer_camera_vertical.ready_for_trigger(
                self.exposure_horiz.get() * 1e6, num_images=2
            )
            self.setup_happened = True

    @kernel
    def _before_start_load_hook(self):
        """
        Before the MOT is loaded, take a background picture
        """

        time_to_wait_after_background_measurement = 3.0 * max(
            self.exposure_vert.get(), self.exposure_horiz.get()
        )

        # Turn on just the 3d beams for a background picture
        self.mot_controller.turn_on_3d_beams()

        self.core.wait_until_mu(now_mu())
        self.mot_measurer_camera_horizontal.trigger()
        self.mot_measurer_camera_vertical.trigger()

        delay(time_to_wait_after_background_measurement)

    @kernel
    def _take_data(self, loading_time):

        delay(loading_time)

        self.core.wait_until_mu(now_mu())

        self.mot_measurer_camera_horizontal.trigger()
        self.mot_measurer_camera_vertical.trigger()

        self.save_data()

    @rpc
    def save_data(self):
        frames_horiz = self.mot_measurer_camera_horizontal.get_frames(
            timeout=1 + self.exposure_horiz.get()
        )
        frames_vert = self.mot_measurer_camera_vertical.get_frames(
            timeout=1 + self.exposure_vert.get()
        )

        timestamp_horiz = frames_horiz[1][0]
        timestamp_vert = frames_vert[1][0]

        image_horiz = frames_horiz[1][1] - frames_horiz[0][1]
        image_vert = frames_vert[1][1] - frames_vert[0][1]

        image_horiz_mean = np.mean(np.array(image_horiz).flat)
        image_vert_mean = np.mean(np.array(image_vert).flat)

        logger.debug("image_horiz.shape = %s", image_horiz.shape)
        logger.debug("image_vert.shape = %s", image_vert.shape)

        self.image_horizontal_timestamp.push(timestamp_horiz)
        self.image_vertical_timestamp.push(timestamp_vert)

        self.image_horizontal_mean.push(image_horiz_mean)
        self.image_vertical_mean.push(image_vert_mean)

        self.image_horizontal.push(image_horiz)
        self.image_vertical.push(image_vert)


MeasureMOTWithPD = make_fragment_scan_exp(MeasureMotWithPDFrag)
MeasureMOTWithCamera = make_fragment_scan_exp(MeasureMotWithCameraFrag)
