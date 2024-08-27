"""
TODO: Pass IJDSettings into Relock single IJD instead of rebinding parameters
"""
import logging
import time
from typing import List
from typing import Optional
from typing import Tuple

from artiq.coredevice.core import Core
from artiq.coredevice.ttl import TTLOut
from artiq.experiment import kernel
from artiq.language.core import delay
from ndscan.experiment import ExpFragment
from ndscan.experiment.entry_point import make_fragment_scan_exp
from ndscan.experiment.parameters import BoolParam
from ndscan.experiment.parameters import BoolParamHandle

import repository.lib.constants as constants
from repository.injected_diodes.set_koheron_controller import SetKoheronFrag
from repository.lib.constants import IJD_DEFAULTS

# from ndscan.experiment import Fragment

logger = logging.getLogger(__name__)


class TriggerIJDRelockFrag(ExpFragment):
    """
    Trigger IJD relock
    """

    def build_fragment(self, *args, **kwargs) -> None:
        self.setattr_param(
            "blue_bool",
            BoolParam,
            "Relock blue?",
            default=True,
        )
        self.blue_bool: BoolParamHandle

        self.setattr_param(
            "red_bool",
            BoolParam,
            "Relock red?",
            default=True,
        )
        self.red_bool: BoolParamHandle

        self.setattr_device("TTL_blue_idjs")
        self.TTL_blue_ijds: TTLOut

    def host_setup(self):
        super().host_setup()

    def run_once(self) -> None:
        self.relock()

    @kernel
    def relock(self) -> None:
        if self.blue_bool:
            self.TTL_blue_ijds.output()
            delay(1e-3)
            self.TTL_blue_ijds.pulse(10e-3)


TriggerIJDRelock = make_fragment_scan_exp(TriggerIJDRelockFrag)
