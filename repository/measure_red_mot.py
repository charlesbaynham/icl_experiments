import logging

from artiq.coredevice.core import Core
from artiq.experiment import delay
from artiq.experiment import kernel
from artiq.experiment import now_mu
from ndscan.experiment import ExpFragment
from ndscan.experiment.entry_point import make_fragment_scan_exp
from ndscan.experiment.parameters import FloatParam
from ndscan.experiment.parameters import FloatParamHandle

from repository.lib.fragments.blue_3d_mot import Blue3DMOTFrag
from repository.lib.fragments.dual_camera_measurer import BGCorrectedMeasurement
from repository.lib.fragments.magnetic_fields import SetMagneticFields
from repository.lib.fragments.red_3d_mot import Red3DMOTFrag

logger = logging.getLogger(__name__)


class MeasureRedMOTFrag(ExpFragment):
    def build_fragment(self):
        self.setattr_device("core")
        self.core: Core

        self.setattr_fragment("blue_mot_controller", Blue3DMOTFrag)
        self.blue_mot_controller: Blue3DMOTFrag

        self.setattr_fragment("red_mot_controller", Red3DMOTFrag)
        self.red_mot_controller: Red3DMOTFrag

        self.setattr_fragment(
            "chamber_2_field_setter",
            SetMagneticFields,
        )
        self.chamber_2_field_setter: SetMagneticFields

        self.setattr_fragment("camera_bg_corrected", BGCorrectedMeasurement)
        self.camera_bg_corrected: BGCorrectedMeasurement

        self.setattr_param(
            "red_loading_time",
            FloatParam,
            "Delay after loading red MOT before taking flourescence measurement",
            default=200e-3,
            unit="ms",
        )
        self.red_loading_time: FloatParamHandle

        # %% Convenience rebound parameters
        self.setattr_param_rebind("ramp_low", self.red_mot_controller)
        self.setattr_param_rebind("ramp_high", self.red_mot_controller)
        self.setattr_param_rebind("ramp_frequency", self.red_mot_controller)
        self.setattr_param_rebind("ramp_type", self.red_mot_controller)

    @kernel
    def run_once(self):
        self.core.break_realtime()

        # Load a blue mot
        self.blue_mot_controller.load_mot(clearout=True)

        # Start sweeping red IJD and turn on the beams
        self.red_mot_controller.turn_on_mot_beams()
        delay(10e-9)
        self.red_mot_controller.start_ramping_red()
        delay(10e-9)
        self.blue_mot_controller.turn_off_3d_and_2d_beams()

        # Wait with atoms hopefully in the red mot
        delay(self.red_loading_time.get())

        # Flash on the blue light and take a photo
        self.blue_mot_controller.turn_on_3d_beams()

        self.core.wait_until_mu(now_mu())
        self.camera_bg_corrected.trigger_signal()

        # Discard the MOT and take a background photo, allowing enough time for
        # the gradient currents to dissipate
        self.chamber_2_field_setter.set_mot_gradient(0.0)
        delay(20e-3)
        self.blue_mot_controller.enable_mot_fields()

        # Take a background photo
        self.core.wait_until_mu(now_mu())
        self.camera_bg_corrected.trigger_background()

        # Save the photos
        self.camera_bg_corrected.save_data()


MeasureRedMOT = make_fragment_scan_exp(MeasureRedMOTFrag)
