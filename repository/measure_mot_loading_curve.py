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


class MeasureMOTFrag(ExpFragment):
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
            "mot_loading_time",
            FloatParam,
            description="Time to wait for the 3D MOT to load",
            default=100 * ms,
            min=0,
            unit="ms",
            step=1,
        )
        self.mot_loading_time: FloatParamHandle

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

        self.setattr_result("photodiode_mean_voltage", FloatChannel)
        self.photodiode_mean_voltage: ResultChannel

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
        delay(25 * ms)
        self.mot_controller.turn_off_3d_and_2d_beams()

        delay(
            100 * ms
        )  # Wait to allow atoms to disperse if there were any hanging around

        # Load MOT and start measuring signal immediately
        self.mot_controller.turn_on_3d_and_2d_beams()

        num_points = int(
            self.mot_loading_time.get() / self.delay_between_trace_points.get()
        )

        trace_data = [0.0] * num_points

        self.mot_measurer.measure_MOT_fluorescence(
            num_points=num_points,
            delay_between_points_mu=self.core.seconds_to_mu(
                self.delay_between_trace_points.get()
            ),
            data=trace_data,
        )

        self.photodiode_voltage.push(trace_data)
        mean_voltage = 0.0
        for i in range(len(trace_data)):
            mean_voltage += trace_data[i]
        mean_voltage /= len(trace_data)
        self.photodiode_mean_voltage.push(mean_voltage)


MeasureMOT = make_fragment_scan_exp(MeasureMOTFrag)
