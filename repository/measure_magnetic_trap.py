from repository.lib.fragments.blue_3d_mot import Blue3DMOTFrag


from ndscan.experiment import ExpFragment

from artiq.coredevice.core import Core
from artiq.coredevice.suservo import Channel as SUServoChannel
from artiq.coredevice.ttl import TTLOut
from artiq.experiment import delay_mu
from artiq.experiment import ms

from artiq.experiment import kernel
from artiq.experiment import now_mu, delay
from ndscan.experiment import Fragment
from ndscan.experiment.parameters import FloatParam
from ndscan.experiment.parameters import FloatParamHandle
from ndscan.experiment.entry_point import make_fragment_scan_exp




class MeasureMagneticTrap(ExpFragment):
    def build_fragment(self):
        self.setattr_device("core")
        self.core: Core

        self.setattr_fragment("mot_controller", Blue3DMOTFrag)
        self.mot_controller: Blue3DMOTFrag

        # The repumpers are not yet driven by ARTIQ, but we do have access to their shutters
        self.repumper_707_shutter:TTLOut = self.get_device("TTL_shutter_707_temporary_shutter")
        self.repumper_679_shutter:TTLOut = self.get_device("TTL_shutter_679_temporary_shutter")

        self.setattr_param(
            "mot_loading_time",
            FloatParam,
            description="Time to wait for the 3D MOT to load",
            default=100*ms,
            min=0,
            unit="ms",
            step=1,
        )
        self.mot_loading_time: FloatParamHandle

        self.setattr_param(
            "dark_time",
            FloatParam,
            description="Time to wait in the dark for the magnetic trap",
            default=100*ms,
            min=0,
            unit="ms",
            step=1,
        )
        self.dark_time: FloatParamHandle

    
    @kernel
    def device_setup(self) -> None:
        self.device_setup_subfragments()

        # Turn on the 2D/3D beams & AOMs,
        # but block the important ones, leaving the repumpers on
        self.mot_controller.enable_mot_beams()
        self.mot_controller.turn_off_push_beam()
        self.mot_controller.turn_off_3d_mot_beams()
        self.repumper_707_shutter.on()
        self.repumper_679_shutter.on()
        
        delay(100*ms) # Wait to allow atoms to disperse if there were any hanging around
        
    @kernel
    def run_once(self):
        self.core.break_realtime()
        delay(50*ms)  # Add some slack for the shutters

        # Load MOT without repumpers
        self.repumper_707_shutter.off()
        self.repumper_679_shutter.off()
        delay(20*ms)  # Surely enough for the SRS shutters to close
        self.mot_controller.turn_on_3d_mot_beams()
        self.mot_controller.turn_on_push_beam()

        # Wait for the MOT to load
        delay(self.mot_loading_time.get())

        # Turn off the push and MOT beams
        self.mot_controller.turn_off_3d_mot_beams()
        self.mot_controller.turn_off_push_beam()

        # Wait for some time while the atoms sit in their magnetic trap
        delay(self.mot_loading_time.get())

        # Turn on the MOT beams (but not the push beam)
        self.mot_controller.turn_on_3d_mot_beams()

        # Measure a trace from the photodiode of how bright the MOT is
        raise NotImplementedError

        # Deluxe:
        # Turn off the MOT beams again and turn on the repumpers
        # Wait for atoms to disappear
        # Turn on the MOT beams again
        # Take background photodiode measurement


MeasureMagneticTrap = make_fragment_scan_exp(MeasureMagneticTrap)
