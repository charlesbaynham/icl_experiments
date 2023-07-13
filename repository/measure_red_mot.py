import logging

from artiq.coredevice.core import Core
from artiq.coredevice.ttl import TTLOut
from artiq.experiment import at_mu
from artiq.experiment import delay
from artiq.experiment import delay_mu
from artiq.experiment import kernel
from artiq.experiment import now_mu
from artiq.experiment import parallel
from artiq.experiment import sequential
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

        self.setattr_fragment(
            "camera_bg_corrected", BGCorrectedMeasurement, hardware_trigger=True
        )
        self.camera_bg_corrected: BGCorrectedMeasurement

        self.setattr_param(
            "red_loading_time",
            FloatParam,
            "Delay after loading red MOT before taking fluorescence measurement",
            default=10e-3,
            unit="ms",
        )
        self.red_loading_time: FloatParamHandle

        self.setattr_param(
            "red_gradient_current",
            FloatParam,
            "Current for gradient coils for red MOT stage",
            default=10,
            unit="A",
        )
        self.red_gradient_current: FloatParamHandle

        # Ensure that both camera are on for the same length of time as the blue
        # fluorescence is pulsed
        self.setattr_param_rebind(
            "camera_exposure",
            self.camera_bg_corrected,
            "exposure_horiz",
            default=200e-6,
            description="Camera exposure and fluorescence pulse length",
        )
        self.camera_bg_corrected.bind_param(
            "exposure_vert",
            self.camera_exposure,
        )
        self.camera_exposure: FloatParamHandle

    @kernel
    def prepare_and_load_blue_mot(self):
        self.core.break_realtime()
        self.blue_mot_controller.init()
        self.red_mot_controller.init()

        # Clear the camera buffer in case we quit a previous sequence midway
        self.camera_bg_corrected.clear()

        self.core.break_realtime()

        # Load a blue mot
        self.blue_mot_controller.load_mot(clearout=True)

    @kernel
    def start_red_loading(self):
        """
        Start sweeping red IJD, turn on the beams and drop the gradient

        Does not advance the timeline
        """

        self.red_mot_controller.turn_on_mot_beams()
        delay_mu(8)
        self.red_mot_controller.start_ramping_red()
        delay_mu(8)
        self.blue_mot_controller.turn_off_3d_and_2d_beams()  # ...but leave repumpers on
        delay_mu(8)
        self.chamber_2_field_setter.set_mot_gradient(self.red_gradient_current.get())

        delay_mu(-3 * 8)

    @kernel
    def pulse_blue_for_image(self):
        # Flash on the blue light
        self.blue_mot_controller.turn_on_3d_beams()
        delay(self.camera_exposure.get())
        self.blue_mot_controller.turn_off_3d_beams()
        delay(self.camera_exposure.get())

    @kernel
    def run_once(self):
        self.prepare_and_load_blue_mot()

        self.start_red_loading()

        # Note that red_loading_time may be negative
        delay(self.red_loading_time.get())

        with parallel:
            self.red_mot_controller.turn_off_mot_beams()
            self.camera_bg_corrected.trigger_signal()
            self.pulse_blue_for_image()

        # Take a nonsense background photo. This currently does nothing and
        # should be coded away
        delay(20e-3)
        self.camera_bg_corrected.trigger_background()

        # Turn the fields back to defaults so eddy currents are gone by the next shot
        self.blue_mot_controller.enable_mot_fields()

        # End of RTIO sequencing. Now we are in real-time.

        # Save the photos
        self.core.wait_until_mu(now_mu())
        self.camera_bg_corrected.save_data()


MeasureRedMOTFrag = make_fragment_scan_exp(MeasureRedMOTFrag)
