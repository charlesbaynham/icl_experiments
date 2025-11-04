import logging

from artiq.experiment import EnumerationValue
from ndscan.experiment import ExpFragment
from ndscan.experiment import make_fragment_scan_exp
from ndscan.experiment.parameters import BoolParam
from ndscan.experiment.parameters import BoolParamHandle
from ndscan.experiment.parameters import FloatParam
from ndscan.experiment.parameters import FloatParamHandle

from repository.lib.fragments.wand_steering import WandSteering

logger = logging.getLogger(__name__)


class WANDSteerFrag(ExpFragment):
    """
    Steer a laser using WAND
    """

    def build_fragment(self):
        self.set_default_scheduling(pipeline_name="wand")

        self.setattr_argument(
            "laser",
            EnumerationValue(
                ["461", "689", "707", "679", "698", "487", "688"], default="461"
            ),
        )
        self.laser: str

        self.setattr_param(
            "offset",
            FloatParam,
            default=0.0,
            unit="MHz",
            description="Offset from setpoint",
        )
        self.offset: FloatParamHandle

        self.setattr_param(
            "set_ref_freq", BoolParam, "Set reference frequency?", default=False
        )
        self.set_ref_freq: BoolParamHandle

        self.setattr_param(
            "reference_freq",
            FloatParam,
            "Reference frequency",
            default=0.0,
            unit="THz",
            scale=1e12,
        )
        self.reference_freq: FloatParamHandle

        self.setattr_fragment("wand_steering", WandSteering)
        self.wand_steering: WandSteering

        self.setattr_param("leave_locked", BoolParam, "Leave locked?", default=False)
        self.leave_locked: BoolParamHandle

    def run_once(self):
        if self.set_ref_freq.get():
            logger.info(
                "Setting laser %s reference frequency to %.0f THz",
                self.laser,
                self.reference_freq.get() * 1e-12,
            )
            self.wand_steering.wand_server.set_reference_freq(
                laser=self.laser, f_ref=self.reference_freq.get()
            )

        self.wand_steering.steer_wand(
            self.laser,
            offset=self.offset.get(),
            timeout=20.0,
            required_accuracy=2e6,
            leave_locked=self.leave_locked.get(),
        )


WANDSteer = make_fragment_scan_exp(WANDSteerFrag)
