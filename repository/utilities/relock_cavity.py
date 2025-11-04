from artiq.coredevice.core import Core
from artiq.language import kernel
from artiq.language.core import kernel
from ndscan.experiment import ExpFragment
from ndscan.experiment import make_fragment_scan_exp
from ndscan.experiment.parameters import BoolParam
from ndscan.experiment.parameters import BoolParamHandle

from repository.lib.fragments.relock_689_and_698 import Control689Shutters
from repository.lib.fragments.relock_689_and_698 import Relock689Frag
from repository.lib.fragments.relock_689_and_698 import Relock698Frag
from repository.lib.fragments.relock_689_and_698 import Relock1379Frag


class SetShutters689Frag(ExpFragment):
    """
    Manually set the 689 and 1379 wavemeter shutters
    """

    def build_fragment(self):
        self.setattr_device("core")
        self.core: Core
        self.setattr_fragment("shutter_control", Control689Shutters)
        self.shutter_control: Control689Shutters

        self.setattr_param(
            "open_689",
            BoolParam,
            default=True,
            description="Open the master 689 shutter",
        )
        self.setattr_param(
            "open_1379",
            BoolParam,
            default=True,
            description="Open the doubled 1379 shutter",
        )
        self.open_689: BoolParamHandle
        self.open_1379: BoolParamHandle

    @kernel
    def run_once(self):
        self.shutter_control.set_shutters(
            open_689=self.open_689.get(), open_1379=self.open_1379.get()
        )


Relock698Cavity = make_fragment_scan_exp(Relock698Frag)
Relock689Cavity = make_fragment_scan_exp(Relock689Frag)
Relock1379Cavity = make_fragment_scan_exp(Relock1379Frag)
SetShutters689 = make_fragment_scan_exp(SetShutters689Frag)
