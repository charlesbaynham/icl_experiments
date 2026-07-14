from enum import Enum
from enum import unique

from ndscan.experiment import ExpFragment
from ndscan.experiment import make_fragment_scan_exp
from ndscan.experiment.parameters import BoolParam
from ndscan.experiment.parameters import BoolParamHandle
from ndscan.experiment.parameters import EnumParam
from ndscan.experiment.parameters import FloatParam
from ndscan.experiment.parameters import FloatParamHandle
from ndscan.experiment.parameters import ParamHandle

from repository.lib.fragments.wand_steering import WandSteering


@unique
class Lasers(Enum):
    laser_461 = "461"
    laser_707 = "707"
    laser_679 = "679"
    laser_688 = "688"
    laser_641 = "641"


class WANDSteerFrag(ExpFragment):
    """
    Steer a laser using WAND
    """

    def build_fragment(self):
        self.set_default_scheduling(pipeline_name="wand")

        self.setattr_param(
            "laser",
            EnumParam,
            "Laser to steer",
            default=Lasers.laser_461,
        )
        self.laser: ParamHandle

        self.setattr_param(
            "offset",
            FloatParam,
            default=0.0,
            unit="MHz",
            description="Offset from setpoint",
        )
        self.offset: FloatParamHandle

        self.setattr_param(
            "initial_gain",
            FloatParam,
            default=1e-6,
            description="Initial gain x 1e-6",
        )
        self.initial_gain: FloatParamHandle

        self.setattr_param(
            "initial_poll_time",
            FloatParam,
            default=5,
            description="Initial poll time",
            unit="s",
        )
        self.initial_poll_time: FloatParamHandle

        self.setattr_param("set_gain", BoolParam, "Set Gain Manually?", default=False)
        self.set_gain: BoolParamHandle

        self.setattr_param(
            "set_poll_time", BoolParam, "Set Poll Time Manually?", default=False
        )
        self.set_poll_time: BoolParamHandle

        self.setattr_param("leave_locked", BoolParam, "Leave locked?", default=True)
        self.leave_locked: BoolParamHandle

        self.setattr_fragment("wand_steering", WandSteering)
        self.wand_steering: WandSteering

    def run_once(self):
        if self.set_gain.get() == True:
            initial_gain = self.initial_gain.get() * 1e-6
        else:
            initial_gain = None

        if self.set_poll_time.get() == True:
            initial_poll_time = self.initial_poll_time.get()
        else:
            initial_poll_time = None

        self.wand_steering.steer_wand(
            self.laser.get().value,
            offset=self.offset.get(),
            timeout=20.0,
            required_accuracy=2e6,
            leave_locked=self.leave_locked.get(),
            initial_gain=initial_gain,
            initial_poll_time=initial_poll_time,
        )


WANDSteer = make_fragment_scan_exp(WANDSteerFrag)
