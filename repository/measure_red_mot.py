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
            "Delay after loading red MOT before taking fluorescence measurement",
            default=200e-3,
            unit="ms",
        )
        self.red_loading_time: FloatParamHandle

        self.setattr_param(
            "red_gradient_current",
            FloatParam,
            "Current for gradient coils for red MOT stage",
            default=20,
            unit="A",
        )
        self.red_gradient_current: FloatParamHandle

        self.setattr_param(
            "camera_latency_margin",
            FloatParam,
            "Time to wait after triggering camera before turning on fluorescence probe",
            default=10e-3,
            unit="ms",
        )
        self.camera_latency_margin: FloatParamHandle

        self.setattr_param(
            "fluorescence_pulse_length",
            FloatParam,
            "Length of fluorescence pulse",
            default=200e-6,
            unit="us",
        )
        self.fluorescence_pulse_length: FloatParamHandle

        # %% Convenience rebound parameters
        self.setattr_param_rebind("ramp_low", self.red_mot_controller)
        self.setattr_param_rebind("ramp_high", self.red_mot_controller)
        # self.setattr_param_rebind(
        #     "ramp_frequency", self.red_mot_controller, unit="kHz", default=30e3
        # )
        self.setattr_param_rebind("ramp_type", self.red_mot_controller)

        self.setattr_param_rebind(
            "camera_exposure", self.camera_bg_corrected, "exposure_horiz"
        )
        self.camera_bg_corrected.bind_param(
            "exposure_vert",
            self.camera_exposure,
        )
        self.camera_exposure: FloatParamHandle

    @kernel
    def run_once(self):
        self.core.break_realtime()
        self.blue_mot_controller.init()
        self.red_mot_controller.init()

        # Clear the camera buffer in case we quit a previous sequence midway
        self.camera_bg_corrected.clear()

        self.core.break_realtime()

        # Load a blue mot
        self.blue_mot_controller.load_mot(clearout=True)

        # Start sweeping red IJD, turn on the beams and drop the gradient
        self.red_mot_controller.turn_on_mot_beams()
        delay(10e-9)
        self.red_mot_controller.start_ramping_red()
        delay(10e-9)
        self.blue_mot_controller.turn_off_3d_and_2d_beams()
        delay(10e-9)
        self.chamber_2_field_setter.set_mot_gradient(self.red_gradient_current.get())

        # Wait with atoms hopefully in the red mot
        delay(self.red_loading_time.get())

        # Start taking picture (or rather, remember when to take a picture)
        t_take_signal = now_mu()

        delay(self.camera_latency_margin.get())

        # Flash on the blue light
        self.blue_mot_controller.turn_on_3d_beams()
        delay(self.fluorescence_pulse_length.get())
        self.blue_mot_controller.turn_off_3d_beams()

        # Discard the MOT to take a background photo, allowing enough time for
        # the gradient currents to dissipate
        self.chamber_2_field_setter.set_mot_gradient(0.0)
        delay(20e-3)

        # TODO: this does nothing. Make it do something or remove it
        t_take_background = now_mu()

        # Turn the fields back on so eddy currents are gone by the next shot
        delay(10e-3)
        self.blue_mot_controller.enable_mot_fields()

        # End of RTIO sequencing. Now we are in real-time, taking the photos with RPCs
        self.core.wait_until_mu(t_take_signal)
        self.camera_bg_corrected.trigger_signal()
        self.core.wait_until_mu(t_take_background)
        self.camera_bg_corrected.trigger_background()

        # Save the photos
        self.camera_bg_corrected.save_data()


MeasureRedMOT = make_fragment_scan_exp(MeasureRedMOTFrag)
