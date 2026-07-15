import logging

from artiq.experiment import BooleanValue
from artiq.experiment import EnvExperiment
from wand.server import ControlInterface as WandServer

from repository.lib import constants

logger = logging.getLogger(__name__)


class SetWandSetpoints(EnvExperiment):
    """
    Set the WAND laser reference frequencies (set points) for the chosen
    isotope.

    This only writes each laser's reference frequency from
    ``constants.WAND_SETPOINTS_87`` / ``WAND_SETPOINTS_88``. It performs no
    steering and does not touch the lock state: no lock, unlock, or convergence
    loop. To also engage the locks and steer onto them, use SwitchIsotope.
    """

    def build(self):
        self.setattr_device("wand_server")
        self.wand_server: WandServer

        self.setattr_argument(
            "sr87",
            BooleanValue(default=constants.USE_SR87),
            tooltip="True = Sr-87, False = Sr-88",
        )

    def run(self):
        setpoints = (
            constants.WAND_SETPOINTS_87 if self.sr87 else constants.WAND_SETPOINTS_88
        )

        for laser, (reference, locked) in setpoints.items():
            logger.info(
                "Setting laser %s reference frequency to %.6f THz",
                laser,
                reference * 1e-12,
            )
            self.wand_server.set_reference_freq(laser=laser, f_ref=reference)

            if locked:
                logger.info("Setting laser %s lock state to %s", laser, locked)
                self.wand_server.lock(laser=laser, set_point=0.0)
