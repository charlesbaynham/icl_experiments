import logging
from typing import *

import toptica_wrapper
from artiq.experiment import *
from toptica_wrapper.driver import TopticaDLCPro

logger = logging.getLogger(__name__)


class SetTopticaState(EnvExperiment):
    """
    Enable or disable the current for the Toptica lasers
    """

    def build(self) -> None:
        self.toptica_device_names = []
        for device_name, device_entry in self.get_device_db().items():
            try:
                if (
                    device_entry["class"] == toptica_wrapper.TopticaDLCPro.__name__
                    and device_entry["module"] == toptica_wrapper.__name__
                ):
                    self.toptica_device_names.append(device_name)
            except (KeyError, TypeError):
                pass

        self.topticas: List[TopticaDLCPro] = [
            self.get_device(d) for d in self.toptica_device_names
        ]

        self.setattr_argument(
            "enable_laser_currents",
            BooleanValue(default=False),
            tooltip="For the lasers being controlled, enable the current?",
        )
        self.enable_laser_currents: bool

        self.toptica_args = []
        for d in self.toptica_device_names:
            arg_name = f"control_{d}"
            self.setattr_argument(
                arg_name,
                BooleanValue(default=False),
                tooltip="Should this laser be controlled?",
                group="Lasers",
            )
            self.toptica_args.append(arg_name)

    def prepare(self):
        self.laser_is_controlled = [getattr(self, a) for a in self.toptica_args]

    def run(self):
        for laser_name, laser, is_controlled in zip(
            self.toptica_device_names, self.topticas, self.laser_is_controlled
        ):
            if is_controlled:
                logger.info(
                    "Setting laser %s's state to %s",
                    laser_name,
                    "ON" if self.enable_laser_currents else "OFF",
                )

                # Open a connection
                laser.get_dlcpro().open()
                laser.get_laser().dl.cc.enabled.set(self.enable_laser_currents)
                laser.get_dlcpro().close()
