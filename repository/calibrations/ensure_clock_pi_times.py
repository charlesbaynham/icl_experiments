"""Client for the full clock-calibration DAG: XODT -> Cal1 (delivery) ->
{Cal2 up-pi, Cal3 down-pi}. Pulling both Rabi calibrations dedups the shared
ClockDeliveryAOMCalibration node, so one run walks the whole DAG and publishes
all three nodes to calibrations.dag / calibrations.status (rendered by the DAG
applet).
"""

import logging

from ndscan.experiment import ExpFragment
from ndscan.experiment.entry_point import make_fragment_scan_exp
from ndscan.experiment.parameters import BoolParam
from ndscan.experiment.parameters import BoolParamHandle

from qbutler.calibration import CalibrationResult
from repository.lib.calibrations.rabi_pi_time import RabiDownPiTimeCalibration
from repository.lib.calibrations.rabi_pi_time import RabiUpPiTimeCalibration

logger = logging.getLogger(__name__)


class EnsureClockPiTimesFrag(ExpFragment):
    def build_fragment(self):
        self.setattr_calibration(RabiUpPiTimeCalibration)
        self.RabiUpPiTimeCalibration: RabiUpPiTimeCalibration
        # Dedups the shared ClockDeliveryAOMCalibration dependency
        self.setattr_calibration(RabiDownPiTimeCalibration)
        self.RabiDownPiTimeCalibration: RabiDownPiTimeCalibration

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
        self.RabiUpPiTimeCalibration.fix_state(force=force)
        self.RabiDownPiTimeCalibration.fix_state(force=force)

        for cal in (self.RabiUpPiTimeCalibration, self.RabiDownPiTimeCalibration):
            result, data = cal.check_state()
            logger.info("%s state: %s (data=%s)", cal, result, data)
            if result != CalibrationResult.OK:
                raise RuntimeError(f"{cal} not OK after fix_state: {result}")


EnsureClockPiTimes = make_fragment_scan_exp(EnsureClockPiTimesFrag)
