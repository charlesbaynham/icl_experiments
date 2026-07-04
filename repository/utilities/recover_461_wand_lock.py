import logging

from ndscan.experiment import ExpFragment
from ndscan.experiment import make_fragment_scan_exp
from ndscan.experiment.parameters import FloatParam
from ndscan.experiment.parameters import FloatParamHandle
from toptica_wrapper.driver import TopticaDLCPro

from repository.lib.fragments.wand_steering import WandSteering

logger = logging.getLogger(__name__)


class Recover461WandLockFrag(ExpFragment):
    """Recover a runaway 461: disable ARC, steer back, leave the WAND lock holding.

    Unlike Recentre461 this does NOT re-enable ARC afterwards — for the case
    where the transfer-cavity error signal is bad and ARC rails the laser
    instead of holding it (seen 2026-07-04: ARC re-enable sent the 461 from
    -1.2 GHz to +46 GHz). Steers to the 2026-07-03 operating setpoint
    (+12.4 MHz) and leaves the WAND software lock engaged at it.
    """

    def build_fragment(self):
        self.set_default_scheduling(pipeline_name="wand")

        self.setattr_fragment("wand_steering", WandSteering)
        self.wand_steering: WandSteering

        self.setattr_param(
            "setpoint",
            FloatParam,
            "461 WAND lock setpoint",
            default=12.4e6,
            unit="MHz",
        )
        self.setpoint: FloatParamHandle

        self.toptica_461: TopticaDLCPro = self.get_device("toptica_461")

    def host_setup(self):
        super().host_setup()
        self.raw_dlcpro = self.toptica_461.get_dlcpro()

    def run_once(self):
        self.raw_dlcpro.open()
        self.laser = self.toptica_461.get_laser()

        self.laser.dl.pc.external_input.enabled.set(False)
        logger.warning(
            "Disabled ARC on 461; steering to %.1f MHz and leaving the WAND lock on",
            1e-6 * self.setpoint.get(),
        )

        self.wand_steering.steer_wand(
            "461",
            offset=self.setpoint.get(),
            timeout=180.0,
            required_accuracy=2e6,
            leave_locked=True,
        )


Recover461WandLock = make_fragment_scan_exp(Recover461WandLockFrag)
