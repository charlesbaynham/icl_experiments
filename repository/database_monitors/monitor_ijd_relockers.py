import logging

from qbutler.calibration import Calibration
from qbutler.calibration import CalibrationResult
from relocker_driver.driver import RelockerDriver

logger = logging.getLogger(__name__)


class _MonitorIJDRelocker(Calibration):
    channels = None
    relocker_name = None

    def build_calibration(self):
        if self.relocker_name is None or self.channels is None:
            raise ValueError("relocker_name and channels must be set in subclasses")

        self.relocker: RelockerDriver = self.get_device(self.relocker_name)
        self.set_timeout(10)

        self.last_unlock_count = None

    def check_own_state(self):
        data = []
        results = []

        for channel in self.channels:
            fields = {}
            try:
                lock_results = self.relocker.get_result_labelled(channel)
                lock_settings = self.relocker.get_settings_labelled(channel)
                levels = self.relocker.get_levels_labelled(channel)
                locked = self.relocker.get_locked(channel)

                unlock_count = self.relocker.get_unlock_count(channel)
                if self.last_unlock_count is None:
                    self.last_unlock_count = unlock_count
                num_new_unlocks = unlock_count - self.last_unlock_count
                logger.info(
                    "Raw unlock_count=%d, num_new_unlocks=%d",
                    unlock_count,
                    num_new_unlocks,
                )
                self.last_unlock_count = unlock_count
                if num_new_unlocks >= 0:
                    # The count of relocks will reset to zero when it rolls over
                    # a 32-bit integer or when the board is rebooted. Ignore
                    # these cases
                    fields["unlock_count"] = num_new_unlocks

                v_current = levels.avg_level
                v_rolling_low = levels.window_level
                v_immediate = levels.most_recent

                auto_mode = int(lock_settings.auto_relock)
                v_low_threshold = lock_settings.v_low_threshold

                fields["v_set_lock"] = lock_results.v_set_lock

                fields["v_current"] = v_current
                fields["v_rolling_low"] = v_rolling_low
                fields["v_immediate"] = v_immediate

                fields["auto_mode"] = auto_mode
                fields["v_low_threshold"] = v_low_threshold

                if auto_mode:
                    if locked:
                        status = "LOCKED"
                    else:
                        status = "UNLOCKED"
                else:
                    status = "IDLE"

                fields["status"] = status

                result = CalibrationResult.OK if locked else CalibrationResult.BAD_DATA

            except AttributeError as e:
                # The connection to the controller failed
                result = CalibrationResult.BAD_DATA
                logger.debug(
                    f"Failed to get lock results from {self.relocker_name} channel {channel}: {e}"
                )
                fields["status"] = "ERROR"

            data.append(
                {
                    "tags": {
                        "type": "ijd_relocker",
                        "relocker_name": self.relocker_name,
                        "relocker_channel": channel,
                    },
                    "fields": fields,
                }
            )
            results.append(result)

        total_result = (
            CalibrationResult.OK
            if all(r == CalibrationResult.OK for r in results)
            else CalibrationResult.BAD_DATA
        )

        return total_result, data


class MonitorBlueIJDRelocker(_MonitorIJDRelocker):
    relocker_name = "blue_relocker"
    channels = [0, 1, 2]


class MonitorRedIJDRelocker(_MonitorIJDRelocker):
    relocker_name = "red_relocker"
    channels = [0]
