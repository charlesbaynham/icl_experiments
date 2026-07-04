"""Client for the blue-MOT calibration alone: check, and fix if required."""

import logging

from ndscan.experiment import ExpFragment
from ndscan.experiment.entry_point import make_fragment_scan_exp
from ndscan.experiment.parameters import BoolParam
from ndscan.experiment.parameters import BoolParamHandle

from qbutler.calibration import CalibrationResult
from repository.lib.calibrations.blue_mot import BlueMOTCalibration

logger = logging.getLogger(__name__)


class EnsureBlueMOTFrag(ExpFragment):
    def build_fragment(self):
        self.setattr_calibration(BlueMOTCalibration)
        self.BlueMOTCalibration: BlueMOTCalibration

        self.setattr_param(
            "force_recalibrate",
            BoolParam,
            "Re-measure and re-optimize unconditionally",
            default=False,
        )
        self.force_recalibrate: BoolParamHandle

    def run_once(self):
        self.BlueMOTCalibration.fix_state(force=self.force_recalibrate.get())

        result, data = self.BlueMOTCalibration.check_state()
        logger.info("Blue MOT state: %s (data=%s)", result, data)
        if result != CalibrationResult.OK:
            raise RuntimeError(f"Blue MOT not OK after fix_state: {result}")


EnsureBlueMOT = make_fragment_scan_exp(EnsureBlueMOTFrag)
