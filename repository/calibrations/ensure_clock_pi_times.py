"""Client for the full clock-calibration DAG: XODT -> Cal1 (delivery) ->
{Cal2 up-pi, Cal3 down-pi}. Pulling both Rabi calibrations dedups the shared
ClockDeliveryAOMCalibration node, so one run walks the whole DAG and publishes
all three nodes to calibrations.dag / calibrations.status (rendered by the DAG
applet).
"""

import logging

from artiq.coredevice.core import Core
from artiq.experiment import kernel
from ndscan.experiment.parameters import BoolParam
from ndscan.experiment.parameters import BoolParamHandle

from qbutler import CalibratedExpFragment
from qbutler import make_calibrated_experiment
from repository.lib.calibrations.rabi_pi_time import RabiDownPiTimeCalibration
from repository.lib.calibrations.rabi_pi_time import RabiUpPiTimeCalibration

logger = logging.getLogger(__name__)

#: Idle wait per iteration so a "run forever" repeat throttles instead of
#: hammering the calibration DAG back-to-back.
IDLE_SLEEP_S = 30.0


class EnsureClockPiTimesFrag(CalibratedExpFragment):
    def build_fragment(self):
        self.setattr_device("core")
        self.core: Core

        self.setattr_calibration(RabiUpPiTimeCalibration)
        self.RabiUpPiTimeCalibration: RabiUpPiTimeCalibration
        # Dedups the shared ClockDeliveryAOMCalibration dependency
        self.setattr_calibration(RabiDownPiTimeCalibration)
        self.RabiDownPiTimeCalibration: RabiDownPiTimeCalibration

        # Maintain both leaves rather than just auto-discovering one: the
        # union walk fixes their shared ClockDeliveryAOMCalibration dependency
        # once, ahead of both.
        self.calibration_targets = [
            self.RabiUpPiTimeCalibration,
            self.RabiDownPiTimeCalibration,
        ]

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


EnsureClockPiTimes = make_calibrated_experiment(EnsureClockPiTimesFrag)
