"""Client for the clock Rabi pi-time DAG: XODT -> delivery -> {up-pi, down-pi}.

Both Rabi calibrations are attached so the shared ClockDeliveryAOMCalibration
node dedups and the applet renders the whole DAG; the escape target is the
up-pi node, whose fix walks the entire shared chain (blue MOT -> ... ->
delivery -> up-pi). A ``@kernel run_once`` calls ``recalibrate_if_needed()`` and
escapes to the host when the chain has drifted.

Note: the escape maintains the up-pi subtree; the down-pi *leaf* is not
re-optimized by this client's escape (it shares every node up to delivery).
Drive EnsureClockPiTimes for the up chain; the down-pi node is recalibrated by
its own client / a scan of RabiDownPiTimeCalibration.
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
        # Dedups the shared ClockDeliveryAOMCalibration dependency and registers
        # the down-pi node in the DAG the applet renders.
        self.setattr_calibration(RabiDownPiTimeCalibration)
        self.RabiDownPiTimeCalibration: RabiDownPiTimeCalibration

        # Two calibrations are attached, so name the DAG the escape maintains.
        self.calibration_target = self.RabiUpPiTimeCalibration

    @kernel
    def run_once(self):
        self.recalibrate_if_needed()
        self.core.wait_until_mu(
            self.core.get_rtio_counter_mu() + self.core.seconds_to_mu(IDLE_SLEEP_S)
        )


EnsureClockPiTimes = make_calibrated_experiment(EnsureClockPiTimesFrag)
