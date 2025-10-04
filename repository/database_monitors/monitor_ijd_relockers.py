import logging

from qbutler.calibration import Calibration
from qbutler.calibration import CalibrationResult
from relocker_driver.driver import RelockerDriver

logger = logging.getLogger(__name__)


class _MonitorIJDRelocker(Calibration):
    channel = None
    relocker_name = None

    def build_calibration(self):
        if self.relocker_name is None or self.channel is None:
            raise ValueError("relocker_name and channel must be set in subclasses")

        self.relocker: RelockerDriver = self.get_device(self.relocker_name)
        self.set_timeout(10)

    def check_own_state(self):
        fields = {}

        try:
            lock_results = self.relocker.get_result_labelled(self.channel)
            v_current, v_rolling_low = self.relocker.get_levels(self.channel)

            fields["v_scan_low"] = lock_results.v_low
            fields["v_set_lock"] = lock_results.v_set_lock
            fields["v_read_lock"] = lock_results.v_read_lock
            fields["v_current"] = v_current
            fields["v_rolling_low"] = v_rolling_low

            locked = lock_results.relock_success
            fields["status"] = "LOCKED" if locked else "UNLOCKED"

            result = CalibrationResult.OK if locked else CalibrationResult.BAD_DATA

        except AttributeError as e:
            # The connection to the controller failed
            result = CalibrationResult.BAD_DATA
            logger.debug(
                f"Failed to get lock results from {self.relocker_name} channel {self.channel}: {e}"
            )
            fields["status"] = "ERROR"

        return result, {
            "tags": {
                "type": "ijd_relocker",
                "relocker_name": self.relocker_name,
                "relocker_channel": self.channel,
            },
            "fields": fields,
        }


class MonitorBlueIJDRelocker0(_MonitorIJDRelocker):
    relocker_name = "blue_relocker"
    channel = 0


class MonitorBlueIJDRelocker1(_MonitorIJDRelocker):
    relocker_name = "blue_relocker"
    channel = 1


class MonitorBlueIJDRelocker2(_MonitorIJDRelocker):
    relocker_name = "blue_relocker"
    channel = 2


class MonitorRedIJDRelocker0(_MonitorIJDRelocker):
    relocker_name = "red_relocker"
    channel = 0
