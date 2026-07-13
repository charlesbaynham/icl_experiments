"""Client for the clock Rabi pi-time DAG: XODT -> delivery -> {up-pi, down-pi}.

Both Rabi calibrations are maintained as escape targets, so the escape walks the
*union* of their DAGs: the shared chain (blue MOT -> ... -> delivery) is fixed
once, then both the up-pi and down-pi leaves are optimized. A ``@kernel
run_once`` calls ``recalibrate_if_needed()`` and escapes to the host when any
node in either chain has drifted.
"""

import logging

from artiq.coredevice.core import Core
from artiq.experiment import kernel

from qbutler import CalibratedExpFragment
from qbutler import make_calibrated_experiment
from repository.lib.calibrations.rabi_pi_time import RabiDownPiTimeCalibration
from repository.lib.calibrations.rabi_pi_time import RabiUpPiTimeCalibration
from repository.lib.experiment_templates.mixins.calibration_dag_applet_mixin import (
    CalibrationDAGAppletMixin,
)

logger = logging.getLogger(__name__)

#: Idle wait per iteration so a "run forever" repeat throttles instead of
#: hammering the calibration DAG back-to-back.
IDLE_SLEEP_S = 30.0


class EnsureClockPiTimesFrag(CalibratedExpFragment, CalibrationDAGAppletMixin):
    def build_fragment(self):
        super().build_fragment()  # applet mixin: sets up ccb
        self.setattr_device("core")
        self.core: Core

        self.setattr_calibration(RabiUpPiTimeCalibration)
        self.RabiUpPiTimeCalibration: RabiUpPiTimeCalibration
        self.setattr_calibration(RabiDownPiTimeCalibration)
        self.RabiDownPiTimeCalibration: RabiDownPiTimeCalibration

        # Maintain both leaves: the escape walks the union of their DAGs, fixing
        # the shared blue-MOT -> ... -> delivery chain once, then both pi times.
        self.calibration_targets = [
            self.RabiUpPiTimeCalibration,
            self.RabiDownPiTimeCalibration,
        ]

    @kernel
    def run_once(self):
        self.recalibrate_if_needed()
        self.core.wait_until_mu(
            self.core.get_rtio_counter_mu() + self.core.seconds_to_mu(IDLE_SLEEP_S)
        )


EnsureClockPiTimes = make_calibrated_experiment(EnsureClockPiTimesFrag)
