import logging

from artiq.experiment import EnvExperiment
from koheron_ctl200_laser_driver import CTL200
from relocker_driver.driver import RelockerDriver

logger = logging.getLogger(__name__)


class TurnOffIJDs(EnvExperiment):
    """Turn off all the injected diodes"""

    def run(self):
        controller_names = [
            k
            for k, v in self.get_device_db().items()
            if (
                ("type" in v and v["type"] == "controller")
                and (
                    "command" in v
                    and "aqctl_koheron_ctl200_laser_driver" in v["command"]
                )
            )
        ]
        if not controller_names:
            raise ValueError("No CTL200 Koheron controllers found in device_db")

        for controller_name in controller_names:
            controller: CTL200 = self.get_device(controller_name)
            logger.info("Turning off controller %s", controller_name)
            controller.turn_off()

        relocker_names = [
            k
            for k, v in self.get_device_db().items()
            if (
                ("type" in v and v["type"] == "controller")
                and ("command" in v and "aqctl_relocker_driver" in v["command"])
            )
        ]

        for relocker_name in relocker_names:
            relocker: RelockerDriver = self.get_device(relocker_name)
            logger.info("Turning off relocker %s", relocker_name)

            for channel in list(range(0, 4)):
                logger.info(
                    "Turning off auto-relock on relocker %s, channel %d",
                    relocker_name,
                    channel,
                )

                try:
                    relocker.set_auto(channel, False)
                except AttributeError as e:
                    logger.error(
                        "Failed to turn off auto-relock on relocker %s, channel %d: %s",
                        relocker_name,
                        channel,
                        e,
                    )
