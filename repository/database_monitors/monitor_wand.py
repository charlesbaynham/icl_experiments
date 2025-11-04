import logging

from qbutler.calibration import Calibration
from qbutler.calibration import CalibrationResult
from sipyco.pc_rpc import Client as RPCClient
from wand.tools import WLMMeasurementStatus

logger = logging.getLogger(__name__)
TIMEOUT = 5
POLL_TIME = 30


class MonitorWAND(Calibration):
    """
    Monitor WAND

    Most of this code is taken from WAND's built-in influx logger, but adapted
    for our database structure / monitor framework
    """

    def build_calibration(self):
        self.set_timeout(10)

    def host_setup(self):
        # TODO: This is risky! It might clash with IPC on the main thread which
        # would cause a crash. It's less likely than before though since it only
        # happens once on startup. A better solution would be to merge
        # https://gitlab.com/aion-physics/code/artiq/qbutler/-/merge_requests/22
        self.wand_controller_config = self.get_device_db()["wand_server"]

        super().host_setup()

    def check_own_state(self):
        measurements = []

        result = CalibrationResult.OK

        try:

            client = RPCClient(
                host=self.wand_controller_config["host"],
                port=self.wand_controller_config["port"],
                timeout=TIMEOUT,
            )

            try:
                lasers = client.get_laser_db()

                for laser in lasers:
                    meas = client.get_freq(
                        laser,
                        age=POLL_TIME,
                        priority=3,
                        get_osa_trace=False,
                        blocking=True,
                        mute=False,
                        offset_mode=False,
                    )
                    status, freq, _ = meas

                    exposure_0 = lasers[laser]["exposure"][0]
                    exposure_1 = lasers[laser]["exposure"][1]

                    if status != WLMMeasurementStatus.OKAY:
                        continue

                    f_ref = lasers[laser]["f_ref"]
                    delta = freq - lasers[laser]["f_ref"]
                    measurements.append(
                        {
                            "tags": {
                                "laser": laser,
                            },
                            "fields": {
                                "freq": freq,
                                "f_ref": f_ref,
                                "detuning": delta,
                                "exposure_0": exposure_0,
                                "exposure_1": exposure_1,
                            },
                        }
                    )
                    logger.debug(
                        "{}: freq {} THz, f_ref {} THz, "
                        "detuning {} MHz".format(laser, freq, f_ref, delta)
                    )
            finally:
                client.close_rpc()

        except OSError:
            result = CalibrationResult.BAD_DATA

        return result, measurements
