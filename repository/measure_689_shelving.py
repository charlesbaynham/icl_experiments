import logging

from artiq.coredevice.core import Core
from artiq.experiment import delay
from artiq.experiment import kernel
from artiq.experiment import now_mu
from ndscan.experiment import ExpFragment
from ndscan.experiment.entry_point import make_fragment_scan_exp
from ndscan.experiment.parameters import FloatParam
from ndscan.experiment.parameters import FloatParamHandle
from ndscan.experiment.result_channels import FloatChannel

from repository.lib.fragments.blue_3d_mot import Blue3DMOTFrag
from repository.lib.fragments.dual_camera_measurer import BGCorrectedMeasurement
from repository.lib.fragments.magnetic_fields import SetMagneticFields
from repository.lib.fragments.red_3d_mot import Red3DMOTFrag

logger = logging.getLogger(__name__)


class Measure689Shelving(ExpFragment):
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
            "toggle_delay",
            FloatParam,
            "Delay before / after 689 toggles",
            default=200e-3,
            unit="ms",
        )
        self.toggle_delay: FloatParamHandle

        # %% core params

        self.mot_loaded = False

    @kernel
    def run_once(self):
        # Clear the camera buffer in case we quit a previous sequence midway
        self.camera_bg_corrected.clear()

        self.core.break_realtime()

        self.red_mot_controller.turn_off_mot_beams()

        # Load a blue mot
        if not self.mot_loaded:
            self.blue_mot_controller.load_mot(clearout=True)
            self.mot_loaded = True

        # Measure
        delay(self.toggle_delay.get())
        self.core.wait_until_mu(now_mu())
        self.camera_bg_corrected.trigger_signal()

        # Turn on the 689
        self.core.break_realtime()
        delay(20e-3)
        self.red_mot_controller.turn_on_mot_beams()

        # Measure
        delay(self.toggle_delay.get())
        self.core.wait_until_mu(now_mu())
        self.camera_bg_corrected.trigger_background()

        # Save the photos
        self.camera_bg_corrected.save_data()


Measure689Shelving = make_fragment_scan_exp(Measure689Shelving)
