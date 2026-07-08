"""Client for the blue-MOT calibration alone: check, and fix if required."""

import logging
import time

from ndscan.experiment.entry_point import make_fragment_scan_exp
from ndscan.experiment.parameters import BoolParam
from ndscan.experiment.parameters import BoolParamHandle

from qbutler.calibration import CalibrationResult
from repository.lib.calibrations.blue_mot import BlueMOTCalibration
from repository.lib.experiment_templates.mixins.calibration_dag_applet_mixin import (
    CalibrationDAGAppletMixin,
)

logger = logging.getLogger(__name__)

#: Idle wait per iteration so a "run forever" repeat throttles instead of
#: hammering the calibration DAG back-to-back.
IDLE_SLEEP_S = 30.0


BlueMOTCalibrationExp = make_fragment_scan_exp(BlueMOTCalibration)


class EnsureBlueMOTFrag(CalibrationDAGAppletMixin):
    def build_fragment(self):
        super().build_fragment()
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

        time.sleep(IDLE_SLEEP_S)


EnsureBlueMOT = make_fragment_scan_exp(EnsureBlueMOTFrag)
