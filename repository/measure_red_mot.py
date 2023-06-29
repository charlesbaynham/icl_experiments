import logging

from artiq.coredevice.core import Core
from artiq.experiment import delay
from artiq.experiment import kernel
from ndscan.experiment import ExpFragment
from ndscan.experiment.entry_point import make_fragment_scan_exp
from ndscan.experiment.parameters import FloatParam

from repository.lib.fragments.blue_3d_mot import Blue3DMOTFrag
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

        # self.setattr_fragment("camera_bg_corrected", BGCorrectedMeasurement)
        # self.camera_bg_corrected: BGCorrectedMeasurement

        self.setattr_param(
            "red_loading_time",
            FloatParam,
            "Delay after loading red MOT before taking flourescence measurement",
            default=200e-3,
            unit="ms",
        )

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

        # # Wait then take a photo
        # self.camera_bg_corrected.trigger_background()
        # self.camera_bg_corrected.trigger_signal()

        # self.camera_bg_corrected.save_data()


MeasureRedMOT = make_fragment_scan_exp(MeasureRedMOTFrag)
