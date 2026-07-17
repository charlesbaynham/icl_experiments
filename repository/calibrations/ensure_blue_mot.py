"""Client for the blue-MOT calibration alone: check, and fix if required."""

import logging

from artiq.coredevice.core import Core
from artiq.experiment import kernel
from ndscan.experiment.entry_point import make_fragment_scan_exp
from ndscan.experiment.parameters import BoolParam
from ndscan.experiment.parameters import BoolParamHandle

from qbutler import CalibratedExpFragment
from qbutler import make_calibrated_experiment
from repository.lib.calibrations.blue_mot import BlueMOTCalibration

logger = logging.getLogger(__name__)

#: Idle wait per iteration so a "run forever" repeat throttles instead of
#: hammering the calibration DAG back-to-back.
IDLE_SLEEP_S = 30.0


BlueMOTCalibrationExp = make_fragment_scan_exp(BlueMOTCalibration)


class EnsureBlueMOTFrag(CalibratedExpFragment):
    def build_fragment(self):
        self.setattr_device("core")
        self.core: Core

        self.setattr_calibration(BlueMOTCalibration)
        self.BlueMOTCalibration: BlueMOTCalibration

        self.setattr_param(
            "force_recalibrate",
            BoolParam,
            "Re-measure and re-optimize unconditionally",
            default=False,
        )
        self.force_recalibrate: BoolParamHandle

    @kernel
    def run_once(self):
        self.recalibrate_if_needed(force=self.force_recalibrate.get())

        self.core.wait_until_mu(
            self.core.get_rtio_counter_mu() + self.core.seconds_to_mu(IDLE_SLEEP_S)
        )


EnsureBlueMOT = make_calibrated_experiment(EnsureBlueMOTFrag)
