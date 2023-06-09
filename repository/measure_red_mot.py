import logging

import numpy as np
from artiq.coredevice.core import Core
from artiq.experiment import delay
from artiq.experiment import kernel
from artiq.experiment import ms
from artiq.experiment import now_mu
from artiq.experiment import rpc
from ndscan.experiment import ExpFragment
from ndscan.experiment import ResultChannel
from ndscan.experiment.entry_point import make_fragment_scan_exp
from ndscan.experiment.parameters import FloatParam
from ndscan.experiment.parameters import FloatParamHandle
from ndscan.experiment.result_channels import FloatChannel
from ndscan.experiment.result_channels import IntChannel
from ndscan.experiment.result_channels import OpaqueChannel

from repository.lib.fragments.blue_3d_mot import Blue3DMOTFrag
from repository.lib.fragments.chamber_photodiode import MOTPhotodiodeMeasurement
from repository.lib.fragments.flir_camera import Chamber2HorizontalCamera
from repository.lib.fragments.flir_camera import Chamber2VerticalCamera
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

    @kernel
    def _take_data(self, loading_time):
        raise NotImplementedError

    @kernel
    def run_once(self):
        self.core.break_realtime()

        delay(10e-6)
        # Turn on the 2D/3D beams & AOMs,
        # but block the important ones, leaving the repumpers on
        self.blue_mot_controller.enable_mot_defaults()
        delay(1 * ms)
        self.blue_mot_controller.turn_off_3d_and_2d_beams()

        delay(
            100 * ms
        )  # Wait to allow atoms to disperse if there were any hanging around

        self._before_start_load_hook()

        # Load MOT and start measuring signal immediately
        self.blue_mot_controller.turn_on_3d_and_2d_beams()

        self._take_data(self.mot_loading_time.get())

    @kernel
    def _before_start_load_hook(self):
        pass


MeasureRedMOT = make_fragment_scan_exp(MeasureRedMOTFrag)
