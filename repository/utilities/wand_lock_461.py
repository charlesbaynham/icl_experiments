import logging

from ndscan.experiment import ExpFragment
from ndscan.experiment import make_fragment_scan_exp
from ndscan.experiment.parameters import FloatParam
from ndscan.experiment.parameters import FloatParamHandle
from toptica_wrapper.driver import TopticaDLCPro

from repository.lib.fragments.wand_steering import WandSteering

logger = logging.getLogger(__name__)


class WandLock461Frag(ExpFragment):
    """
    Disable the 461 transfer-cavity ARC and hold the 461 on a direct WAND lock.

    Backup for when the transfer cavity is degraded and the ARC relock will not
    hold: it disables the ARC (external input) so it cannot fight the wavemeter,
    then locks the 461 directly to the WAND at the configured ``setpoint`` and
    leaves it locked. The setpoint defaults to 0 (lock at the WAND reference); a
    non-zero value is only a temporary calibration offset to compensate wavemeter
    reference drift. Noisier than the transfer-cavity lock but more robust. The
    ARC is left DISABLED on exit; run Recentre461 to hand control back to the ARC.
    """

    def build_fragment(self):
        self.set_default_scheduling(pipeline_name="wand")

        self.setattr_param(
            "setpoint",
            FloatParam,
            "WAND lock setpoint, as an offset from the WAND reference",
            default=0.0,
            unit="MHz",
            scale=1e6,
        )
        self.setpoint: FloatParamHandle

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

        # Disable ARC so the transfer-cavity relock does not fight the WAND lock
        self.laser.dl.pc.external_input.enabled.set(False)
        logger.warning("Disabled ARC on 461")

        setpoint = self.setpoint.get()
        self.wand_steering.steer_wand(
            "461",
            offset=setpoint,
            timeout=60.0,
            required_accuracy=2e6,
            leave_locked=True,
        )

        logger.warning(
            "461 held on WAND lock at %.3f MHz; ARC left disabled", setpoint * 1e-6
        )


WandLock461 = make_fragment_scan_exp(WandLock461Frag)
