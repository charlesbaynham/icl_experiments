import logging

from ndscan.experiment import ExpFragment
from ndscan.experiment import make_fragment_scan_exp
from toptica_wrapper.driver import TopticaDLCPro

from repository.lib import constants
from repository.lib.fragments.wand_steering import WandSteering

logger = logging.getLogger(__name__)


class Recentre461Frag(ExpFragment):
    """
    Recentre the 461 for the transfer cavity lock
    """

    def build_fragment(self):
        self.set_default_scheduling(pipeline_name="wand")

        self.setattr_fragment("wand_steering", WandSteering)
        self.wand_steering: WandSteering

        self.toptica_461: TopticaDLCPro = self.get_device("toptica_461")

    def host_setup(self):
        super().host_setup()

        self.raw_dlcpro = self.toptica_461.get_dlcpro()

    def run_once(self):
        # Open a connection
        self.raw_dlcpro.open()
        self.laser = self.toptica_461.get_laser()

        # Disable ARC
        self.laser.dl.pc.external_input.enabled.set(False)

        # Steer the 461 back to its nominal setpoint
        self.wand_steering.steer_wand(
            "461",
            offset=0,
            timeout=20.0,
            required_accuracy=2e6,
            leave_locked=False,
        )

        # Reenable ARC
        self.laser.dl.pc.external_input.signal.set(
            constants.TRANSFER_CAVITY_461_CHANNEL
        )
        self.laser.dl.pc.external_input.factor.set(constants.TRANSFER_CAVITY_461_GAIN)
        self.laser.dl.pc.external_input.enabled.set(True)

        fac = self.laser.dl.pc.external_input.factor.get()
        channel = self.laser.dl.pc.external_input.signal.get()
        logger.warning(f"Reenabled ARC on 461 with channel {channel} and gain {fac}")


Recentre461 = make_fragment_scan_exp(Recentre461Frag)
