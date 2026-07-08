"""Client experiment that *uses* the red-MOT calibration.

Running this proves the qbutler DAG contract: the whole chain (blue MOT →
red MOT) is checked, and anything BAD/expired is re-optimized, before the
client proceeds. Within the check-state timeout a re-submission does nothing
at all (state is recalled from the calibrations.status dataset).
"""

import logging
import time

from ndscan.experiment.entry_point import make_fragment_scan_exp
from ndscan.experiment.parameters import BoolParam
from ndscan.experiment.parameters import BoolParamHandle

from qbutler.calibration import CalibrationResult
from repository.lib.calibrations.red_mot import RedMOTCalibration
from repository.lib.experiment_templates.mixins.calibration_dag_applet_mixin import (
    CalibrationDAGAppletMixin,
)

logger = logging.getLogger(__name__)

#: Idle wait per iteration so a "run forever" repeat throttles instead of
#: hammering the calibration DAG back-to-back.
IDLE_SLEEP_S = 30.0


class EnsureRedMOTFrag(CalibrationDAGAppletMixin):
    def build_fragment(self):
        super().build_fragment()
        self.setattr_calibration(RedMOTCalibration)
        self.RedMOTCalibration: RedMOTCalibration

        self.setattr_param(
            "force_recalibrate",
            BoolParam,
            "Re-measure and re-optimize the whole chain unconditionally",
            default=False,
        )
        self.force_recalibrate: BoolParamHandle

    def run_once(self):
        self.RedMOTCalibration.fix_state(force=self.force_recalibrate.get())

        result, data = self.RedMOTCalibration.check_state()
        logger.info("Red MOT chain state: %s (data=%s)", result, data)
        if result != CalibrationResult.OK:
            raise RuntimeError(f"Red MOT chain not OK after fix_state: {result}")

        time.sleep(IDLE_SLEEP_S)


EnsureRedMOT = make_fragment_scan_exp(EnsureRedMOTFrag)
