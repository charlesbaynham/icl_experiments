"""
TODO: Pass IJDSettings into Relock single IJD instead of rebinding parameters
"""

import logging

from artiq.coredevice.core import Core
from artiq.coredevice.ttl import TTLOut
from artiq.language import kernel
from artiq.language.core import delay
from ndscan.experiment import ExpFragment
from ndscan.experiment.entry_point import make_fragment_scan_exp
from ndscan.experiment.parameters import BoolParam
from ndscan.experiment.parameters import BoolParamHandle

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

        self.setattr_device("core")
        self.core: Core

        self.setattr_device("ttl12")
        self.ttl12: TTLOut

    def host_setup(self):
        super().host_setup()

    @kernel
    def run_once(self) -> None:
        self.core.break_realtime()
        self.relock()

    @kernel
    def relock(self) -> None:
        if self.blue_bool:
            delay(1e-3)
            self.ttl12.pulse(10e-3)

    @kernel
    def run(self):
        self.relock()


TriggerIJDRelock = make_fragment_scan_exp(TriggerIJDRelockFrag)
