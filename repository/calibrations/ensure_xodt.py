"""Client for the full clock-calibration DAG: XODT -> Cal1 (delivery) ->
{Cal2 up-pi, Cal3 down-pi}. Pulling both Rabi calibrations dedups the shared
ClockDeliveryAOMCalibration node, so one run walks the whole DAG and publishes
all three nodes to calibrations.dag / calibrations.status (rendered by the DAG
applet).
"""

import logging
import time

from ndscan.experiment import ExpFragment
from ndscan.experiment.entry_point import make_fragment_scan_exp
from ndscan.experiment.parameters import BoolParam
from ndscan.experiment.parameters import BoolParamHandle

from qbutler.calibration import CalibrationResult
from repository.lib.calibrations.xodt_calibration import SingleXODTCalibration

logger = logging.getLogger(__name__)

#: Idle wait per iteration so a "run forever" repeat throttles instead of
#: hammering the calibration DAG back-to-back.
IDLE_SLEEP_S = 30.0


class EnsureXODTFrag(ExpFragment):
    def build_fragment(self):
        self.setattr_calibration(SingleXODTCalibration)
        self.SingleXODTCalibration: SingleXODTCalibration

        self.setattr_param(
            "force_recalibrate",
            BoolParam,
            "Re-measure and re-optimize unconditionally",
            default=False,
        )
        self.force_recalibrate: BoolParamHandle

    def run_once(self):
        force = self.force_recalibrate.get()
        # Up first fixes the shared delivery node; down then reuses it.
        self.SingleXODTCalibration.fix_state(force=force)

        result, data = self.SingleXODTCalibration.check_state()
        logger.info("%s state: %s (data=%s)", self.SingleXODTCalibration, result, data)
        if result != CalibrationResult.OK:
            raise RuntimeError(
                f"{self.SingleXODTCalibration} not OK after fix_state: {result}"
            )

        time.sleep(IDLE_SLEEP_S)


EnsureXODT = make_fragment_scan_exp(EnsureXODTFrag)
