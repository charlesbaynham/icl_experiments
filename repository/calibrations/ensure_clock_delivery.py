"""Client that keeps the clock delivery-AOM centring chain healthy while it runs.

Fixing the delivery node walks the whole blue -> red -> coarse -> refined chain
furthest-first. A ``@kernel run_once`` calls ``recalibrate_if_needed()`` and
escapes to the host when any node has drifted.
"""

import logging

from artiq.coredevice.core import Core
from artiq.experiment import kernel

from qbutler import CalibratedExpFragment
from qbutler import make_calibrated_experiment
from repository.lib.calibrations.clock_delivery import ClockDeliveryAOMCalibration
from repository.lib.experiment_templates.mixins.calibration_dag_applet_mixin import (
    CalibrationDAGAppletMixin,
)

logger = logging.getLogger(__name__)

#: Idle wait per iteration so a "run forever" repeat throttles instead of
#: hammering the calibration DAG back-to-back.
IDLE_SLEEP_S = 30.0


class EnsureClockDeliveryFrag(CalibratedExpFragment, CalibrationDAGAppletMixin):
    def build_fragment(self):
        super().build_fragment()  # applet mixin: sets up ccb
        self.setattr_device("core")
        self.core: Core

        self.setattr_calibration(ClockDeliveryAOMCalibration)
        self.ClockDeliveryAOMCalibration: ClockDeliveryAOMCalibration

    @kernel
    def run_once(self):
        self.recalibrate_if_needed()
        self.core.wait_until_mu(
            self.core.get_rtio_counter_mu() + self.core.seconds_to_mu(IDLE_SLEEP_S)
        )


EnsureClockDelivery = make_calibrated_experiment(EnsureClockDeliveryFrag)
