import logging

from artiq.coredevice.core import Core
from artiq.coredevice.ttl import TTLOut
from artiq.experiment import delay
from artiq.experiment import delay_mu
from artiq.experiment import kernel
from artiq.experiment import ms
from artiq.experiment import TFloat
from artiq.experiment import TInt32
from artiq.experiment import TList
from ndscan.experiment import ExpFragment
from ndscan.experiment import Fragment
from ndscan.experiment import ResultChannel
from ndscan.experiment.entry_point import make_fragment_scan_exp
from ndscan.experiment.parameters import FloatParam
from ndscan.experiment.parameters import FloatParamHandle
from ndscan.experiment.parameters import IntParam
from ndscan.experiment.parameters import IntParamHandle
from ndscan.experiment.result_channels import OpaqueChannel

from repository.lib.fragments.blue_3d_mot import Blue3DMOTFrag
from repository.lib.fragments.read_adc import ReadSUServoADC


logger = logging.getLogger(__file__)


class MOTPhotodiodeMeasurement(Fragment):
    def build_fragment(self):
        self.setattr_device("core")
        self.core: Core

        photodiode_suservo_name, photodiode_suservo_channel = self.get_device_db()[
            "mot_photodiode_sampler_config"
        ]

        # Load the ADC utility subfragment
        self.setattr_fragment(
            "adc_reader",
            ReadSUServoADC,
            self.get_device(photodiode_suservo_name),
            photodiode_suservo_channel,
        )
        self.adc_reader: ReadSUServoADC

    @kernel
    def measure_MOT_fluorescence(
        self, num_points: TInt32, delay_between_points_mu: TFloat
    ) -> TList(TFloat):
        data = [0.0] * num_points

        for i in range(num_points):
            data[i] = self.adc_reader.read_adc()
            delay_mu(delay_between_points_mu)

        return data


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

    @kernel
    def device_setup(self) -> None:
        self.device_setup_subfragments()

        self.core.break_realtime()
        delay(20 * ms)

        # Turn on the 2D/3D beams & AOMs,
        # but block the important ones, leaving the repumpers on
        self.mot_controller.turn_off_push_beam()
        self.mot_controller.turn_off_3d_mot_beams()
        self.mot_controller.enable_mot_beams()
        self.repumper_707_shutter.on()
        self.repumper_679_shutter.on()

        delay(
            100 * ms
        )  # Wait to allow atoms to disperse if there were any hanging around

    @kernel
    def run_once(self):
        self.core.break_realtime()
        delay(50 * ms)  # Add some slack for the shutters

        logger.warning("1")

        # Load MOT without repumpers
        self.repumper_707_shutter.off()
        self.repumper_679_shutter.off()
        delay(20 * ms)  # Surely enough for the SRS shutters to close
        self.mot_controller.turn_on_3d_mot_beams()
        self.mot_controller.turn_on_push_beam()

        logger.warning("2")

        # Wait for the MOT to load
        delay(self.mot_loading_time.get())

        logger.warning("3")

        # Turn off the push and MOT beams
        self.mot_controller.turn_off_3d_mot_beams()
        self.mot_controller.turn_off_push_beam()

        logger.warning("4")

        # Wait for some time while the atoms sit in their magnetic trap
        delay(self.mot_loading_time.get())

        logger.warning("5")

        # Turn on the MOT beams (but not the push beam)
        self.mot_controller.turn_on_3d_mot_beams()

        logger.warning("6")

        # Measure a trace from the photodiode of how bright the MOT is
        trace_data = self.mot_measurer.measure_MOT_fluorescence(
            num_points=self.num_trace_points.get(),
            delay_between_points_mu=self.core.seconds_to_mu(
                self.delay_between_trace_points.get()
            ),
        )

        logger.warning("7")

        self.photodiode_voltage.push(trace_data)

        logger.warning("8")

        # Deluxe:
        # Turn off the MOT beams again and turn on the repumpers
        # Wait for atoms to disappear
        # Turn on the MOT beams again
        # Take background photodiode measurement


MeasureMagneticTrap = make_fragment_scan_exp(MeasureMagneticTrapFrag)
