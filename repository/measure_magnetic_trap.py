from artiq.coredevice.core import Core
from artiq.coredevice.ttl import TTLOut
from artiq.experiment import delay
from artiq.experiment import kernel
from artiq.experiment import ms
from artiq.experiment import ns
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


class MeasureMagneticTrapFrag(ExpFragment):
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
            default=100 * ms,
            min=0,
            unit="ms",
            step=1,
        )
        self.magnetic_trap_loading_time: FloatParamHandle

        self.setattr_param(
            "dark_time",
            FloatParam,
            description="Time to wait in the dark for the magnetic trap",
            default=100 * ms,
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
            default=1 * ms,
            unit="ms",
            min=1 * ms,
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
        delay(20 * ms)

    @kernel
    def run_once(self):
        # Turn on the 2D/3D beams & AOMs,
        # but block the important ones, leaving the repumpers on and allowing the AOMs to warm
        self.mot_controller.enable_mot_beams()
        self.repumper_707_shutter.on()
        self.repumper_679_shutter.on()
        delay(20 * ns)
        self.mot_controller.turn_off_push_beam()
        delay(21 * ms)
        self.mot_controller.turn_off_2d_mot_beams()
        delay(21 * ms)
        self.mot_controller.turn_off_3d_mot_beams()

        delay(
            100 * ms
        )  # Wait to allow atoms to disperse if there were any hanging around

        # Load MOT with repumpers disabled to drain into mag. trap
        self.mot_controller.turn_on_2d_mot_beams()
        delay(21 * ms)
        self.mot_controller.turn_on_3d_mot_beams()
        delay(21 * ms)
        self.mot_controller.turn_on_push_beam()
        delay(21 * ms)
        delay(20 * ns)
        self.repumper_707_shutter.off()
        self.repumper_679_shutter.off()

        # Wait for the MOT to load
        delay(self.magnetic_trap_loading_time.get())

        # Turn off the MOT beams
        self.mot_controller.turn_off_2d_mot_beams()
        delay(21 * ms)
        self.mot_controller.turn_off_3d_mot_beams()
        delay(21 * ms)
        self.mot_controller.turn_off_push_beam()

        # Wait for some time while the atoms sit in their magnetic trap
        delay(self.dark_time.get())

        # Turn on the MOT beams and the repumpers (but not the push beam)
        self.mot_controller.turn_on_3d_mot_beams()
        delay(20 * ms)
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


MeasureMagneticTrap = make_fragment_scan_exp(MeasureMagneticTrapFrag)
