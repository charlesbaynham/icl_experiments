from artiq.experiment import EnumerationValue
from ndscan.experiment import ExpFragment
from ndscan.experiment import make_fragment_scan_exp
from ndscan.experiment.parameters import BoolParam
from ndscan.experiment.parameters import BoolParamHandle
from ndscan.experiment.parameters import FloatParam
from ndscan.experiment.parameters import FloatParamHandle

from repository.lib.fragments.wand_steering import WandSteering


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

        self.setattr_fragment("wand_steering", WandSteering)
        self.wand_steering: WandSteering

        self.setattr_param("leave_locked", BoolParam, "Leave locked?", default=False)
        self.leave_locked: BoolParamHandle

    def run_once(self):
        self.wand_steering.steer_wand(
            self.laser,
            offset=self.offset.get(),
            timeout=20.0,
            required_accuracy=2e6,
            leave_locked=self.leave_locked.get(),
        )


WANDSteer = make_fragment_scan_exp(WANDSteerFrag)
