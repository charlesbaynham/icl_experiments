"""Client experiment that *uses* the red-MOT calibration.

Running this proves the qbutler DAG contract: the whole chain (blue MOT →
red MOT) is checked, and anything BAD/expired is re-optimized, before the
client proceeds. Within the check-state timeout a re-submission does nothing
at all (state is recalled from the calibrations.status dataset).
"""

import logging
import time

from artiq.master.worker_impl import CCB
from ndscan.experiment import ExpFragment
from ndscan.experiment.entry_point import make_fragment_scan_exp
from ndscan.experiment.parameters import BoolParam
from ndscan.experiment.parameters import BoolParamHandle

from qbutler.calibration import CalibrationResult
from repository.lib.calibrations.red_mot import RedMOTCalibration

logger = logging.getLogger(__name__)

DAG_APPLET_CMD = (
    "${python} -m repository.lib.applets.qbutler_dag_applet "
    "calibrations.dag calibrations.status"
)

#: Idle wait per iteration so a "run forever" repeat throttles instead of
#: hammering the calibration DAG back-to-back.
IDLE_SLEEP_S = 30.0


class EnsureRedMOTFrag(ExpFragment):
    def build_fragment(self):
        self.setattr_calibration(RedMOTCalibration)
        self.RedMOTCalibration: RedMOTCalibration

        self.setattr_param(
            "force_recalibrate",
            BoolParam,
            "Re-measure and re-optimize the whole chain unconditionally",
            default=False,
        )
        self.force_recalibrate: BoolParamHandle

        self.setattr_device("ccb")
        self.ccb: CCB

    def host_setup(self):
        super().host_setup()
        self.ccb.issue("create_applet", "Calibration DAG", DAG_APPLET_CMD)

    def run_once(self):
        self.RedMOTCalibration.fix_state(force=self.force_recalibrate.get())

        result, data = self.RedMOTCalibration.check_state()
        logger.info("Red MOT chain state: %s (data=%s)", result, data)
        if result != CalibrationResult.OK:
            raise RuntimeError(f"Red MOT chain not OK after fix_state: {result}")

        time.sleep(IDLE_SLEEP_S)


EnsureRedMOT = make_fragment_scan_exp(EnsureRedMOTFrag)
