"""Client experiment that *uses* the red-MOT calibration.

Running this proves the qbutler DAG contract: the whole chain (blue MOT →
red MOT) is checked, and anything BAD/expired is re-optimized, before the
client proceeds. Within the check-state timeout a re-submission does nothing
at all (state is recalled from the calibrations.status dataset).
"""

import logging

from artiq.coredevice.core import Core
from artiq.experiment import kernel
from ndscan.experiment.parameters import BoolParam
from ndscan.experiment.parameters import BoolParamHandle

from qbutler import CalibratedExpFragment
from qbutler import make_calibrated_experiment
from repository.lib.calibrations.red_mot import RedMOTCalibration

logger = logging.getLogger(__name__)

#: Idle wait per iteration so a "run forever" repeat throttles instead of
#: hammering the calibration DAG back-to-back.
IDLE_SLEEP_S = 30.0


class EnsureRedMOTFrag(CalibratedExpFragment):
    def build_fragment(self):
        self.setattr_device("core")
        self.core: Core

        self.setattr_calibration(RedMOTCalibration)
        self.RedMOTCalibration: RedMOTCalibration

        self.setattr_param(
            "force_recalibrate",
            BoolParam,
            "Re-measure and re-optimize the whole chain unconditionally",
            default=False,
        )
        self.force_recalibrate: BoolParamHandle

    @kernel
    def run_once(self):
        self.recalibrate_if_needed(force=self.force_recalibrate.get())

        self.core.wait_until_mu(
            self.core.get_rtio_counter_mu() + self.core.seconds_to_mu(IDLE_SLEEP_S)
        )


EnsureRedMOT = make_calibrated_experiment(EnsureRedMOTFrag)
