import logging

import numpy as np
from artiq.coredevice.core import Core
from artiq.coredevice.ttl import TTLOut
from artiq.experiment import delay
from artiq.experiment import kernel
from artiq.experiment import now_mu
from artiq.experiment import rpc
from ndscan.experiment import ExpFragment
from ndscan.experiment import ResultChannel
from ndscan.experiment.entry_point import make_fragment_scan_exp
from ndscan.experiment.parameters import FloatParam
from ndscan.experiment.parameters import FloatParamHandle
from ndscan.experiment.parameters import IntParam
from ndscan.experiment.parameters import IntParamHandle
from ndscan.experiment.result_channels import FloatChannel
from ndscan.experiment.result_channels import OpaqueChannel

from repository.lib.fragments.blue_3d_mot import Blue3DMOTFrag
from repository.lib.fragments.blue_3d_mot import MOTPhotodiodeMeasurement
from repository.lib.fragments.flir_camera import Chamber2Camera

logger = logging.getLogger(__name__)


class MeasureMagneticTrapWithPDFrag(ExpFragment):
    def build_fragment(self):
        self.setattr_device("core")
        self.core: Core

        self.setattr_fragment("mot_controller", Blue3DMOTFrag)
        self.mot_controller: Blue3DMOTFrag

        self.setattr_fragment("mot_measurer", MOTPhotodiodeMeasurement)
        self.mot_measurer: MOTPhotodiodeMeasurement

        # The repumpers are not yet driven by ARTIQ, but we do have access to their shutters
        self.repumper_707_shutter: TTLOut = self.get_device(
            "TTL_shutter_707_temporary_shutter"
        )
        self.repumper_679_shutter: TTLOut = self.get_device(
            "TTL_shutter_679_temporary_shutter"
        )

        self.setattr_param(
            "magnetic_trap_loading_time",
            FloatParam,
            description="Time to drain into the mag trap for",
            default=100e-3,
            min=0,
            unit="ms",
            step=1,
        )
        self.magnetic_trap_loading_time: FloatParamHandle

        self.setattr_param(
            "dark_time",
            FloatParam,
            description="Time to wait in the dark for the magnetic trap",
            default=100e-3,
            min=0,
            unit="ms",
            step=1,
        )
        self.dark_time: FloatParamHandle

        self.setattr_param(
            "num_trace_points",
            IntParam,
            description="Number of points to take in photodiode trace",
            default=100,
            min=1,
        )
        self.num_trace_points: IntParamHandle

        self.setattr_param(
            "delay_between_trace_points",
            FloatParam,
            description="Delay between points in the photodiode trace",
            default=1e-3,
            unit="ms",
            min=1e-3,
            step=1,
        )
        self.delay_between_trace_points: FloatParamHandle

        # Add output channel
        self.setattr_result("photodiode_voltage", OpaqueChannel)
        self.photodiode_voltage: ResultChannel

        self.setattr_result("final_voltage", FloatChannel)
        self.final_voltage: ResultChannel

    @kernel
    def device_setup(self) -> None:
        self.device_setup_subfragments()

        self.core.break_realtime()
        delay(20e-3)

    @kernel
    def run_once(self):
        # Turn on the 2D/3D beams & AOMs,
        # but block the important ones, leaving the repumpers on and allowing the AOMs to warm
        self.mot_controller.enable_mot_defaults()
        self.repumper_707_shutter.on()
        self.repumper_679_shutter.on()
        delay(20e-9)
        self.mot_controller.turn_off_3d_and_2d_beams()

        delay(
            100e-3
        )  # Wait to allow atoms to disperse if there were any hanging around

        # Load MOT with repumpers disabled to drain into mag. trap
        self.mot_controller.turn_on_3d_and_2d_beams()
        self.repumper_707_shutter.off()
        self.repumper_679_shutter.off()

        # Wait for the MOT to load
        delay(self.magnetic_trap_loading_time.get())

        # Turn off the MOT beams
        self.mot_controller.turn_off_3d_and_2d_beams()

        # Wait for some time while the atoms sit in their magnetic trap
        delay(self.dark_time.get())

        # Turn on the MOT beams and the repumpers (but not the push beam)
        self.mot_controller.turn_on_3d_beams()
        # Delay to be sure that the atoms are not being repumped before the MOT light comes on
        delay(20e-3)
        self.repumper_707_shutter.on()
        self.repumper_679_shutter.on()

        # Measure a trace from the photodiode of how bright the MOT is
        num_points = self.num_trace_points.get()
        trace_data = [0.0] * num_points

        self.mot_measurer.measure_MOT_fluorescence(
            num_points=num_points,
            delay_between_points_mu=self.core.seconds_to_mu(
                self.delay_between_trace_points.get()
            ),
            data=trace_data,
        )

        self.photodiode_voltage.push(trace_data)
        self.final_voltage.push(trace_data[-1])

        # Deluxe:
        # Turn off the MOT beams again and turn on the repumpers
        # Wait for atoms to disappear
        # Turn on the MOT beams again
        # Take background photodiode measurement


class MeasureMagneticTrapWithCameraFrag(ExpFragment):
    def build_fragment(self):
        self.setattr_device("core")
        self.core: Core

        self.setattr_fragment("mot_controller", Blue3DMOTFrag)
        self.mot_controller: Blue3DMOTFrag

        self.setattr_fragment("camera_frag", Chamber2Camera)
        self.camera_frag: Chamber2Camera

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
            default=100e-3,
            min=0,
            unit="ms",
            step=1,
        )
        self.mot_loading_time: FloatParamHandle

        self.setattr_param(
            "dark_time",
            FloatParam,
            description="Time to wait in the dark for the magnetic trap",
            default=100e-3,
            min=0,
            unit="ms",
            step=1,
        )
        self.dark_time: FloatParamHandle

        self.setattr_param(
            "wait_before_photo",
            FloatParam,
            description="Time to wait before imaging",
            default=20e-3,
            min=0,
            unit="ms",
            step=1,
        )
        self.wait_before_photo: FloatParamHandle

        self.setattr_param(
            "exposure",
            FloatParam,
            description="Image exposure",
            default=1e-3,
            min=0,
            unit="ms",
            step=1,
        )
        self.exposure: FloatParamHandle

        # Add output channels
        self.setattr_result("mot_images", OpaqueChannel)
        self.mot_images: ResultChannel

        self.setattr_result("mot_image_timestamps", OpaqueChannel)
        self.mot_image_timestamps: ResultChannel

        self.setattr_result("mot_integrated_brightness", FloatChannel)
        self.mot_integrated_brightness: ResultChannel

    @rpc
    def save_data(self):
        image_data = self.camera_frag.get_frames()
        assert len(image_data) == 1

        timestamp, image = image_data[0]
        brightness = np.sum(np.array(image).flatten())

        self.mot_image_timestamps.push(timestamp)
        self.mot_images.push(image)
        self.mot_integrated_brightness.push(brightness)

        logger.debug("Saving data completed")

    @kernel
    def run_once(self):
        self.camera_frag.ready_for_trigger(
            exposure_us=self.exposure.get() * 1e6, num_images=1
        )

        self.core.break_realtime()
        delay(20e-3)

        # Turn on the 2D/3D beams & AOMs,
        # but block the important ones, leaving the repumpers on
        self.mot_controller.enable_mot_defaults()
        self.repumper_707_shutter.on()
        self.repumper_679_shutter.on()
        delay(20e-9)
        self.mot_controller.turn_off_3d_and_2d_beams()

        delay(
            100e-3
        )  # Wait to allow atoms to disperse if there were any hanging around

        # Load MOT without repumpers
        self.repumper_707_shutter.off()
        self.repumper_679_shutter.off()
        delay(20e-3)  # Surely enough for the SRS shutters to close
        self.mot_controller.turn_on_3d_and_2d_beams()

        # Wait for the MOT to load
        delay(self.mot_loading_time.get())

        # Turn off the push and MOT beams
        self.mot_controller.turn_off_3d_and_2d_beams()

        # Wait for some time while the atoms sit in their magnetic trap
        delay(self.dark_time.get())

        # Turn on the MOT beams and the repumpers (but not the push beam)
        self.repumper_707_shutter.on()
        self.repumper_679_shutter.on()
        delay(20e-9)
        self.mot_controller.turn_on_3d_beams()

        # Take a photo
        delay(self.wait_before_photo.get())
        self.core.wait_until_mu(now_mu())

        self.camera_frag.trigger()

        # Trigger the host to retrieve the data
        self.save_data()

        # Deluxe:
        # Turn off the MOT beams again and turn on the repumpers
        # Wait for atoms to disappear
        # Turn on the MOT beams again
        # Take background photodiode measurement


MeasureMagneticTrapWithPhotodiode = make_fragment_scan_exp(
    MeasureMagneticTrapWithPDFrag
)
MeasureMagneticTrapWithCamera = make_fragment_scan_exp(
    MeasureMagneticTrapWithCameraFrag
)
