import logging
import time
from typing import Dict
from typing import List
from typing import Tuple
from typing import Type
from typing import TYPE_CHECKING

import numpy as np
from artiq.coredevice.core import Core
from artiq.coredevice.ttl import TTLOut
from artiq.experiment import host_only
from artiq.experiment import kernel
from artiq.experiment import portable
from artiq.experiment import rpc
from artiq.experiment import TBool
from ndscan.experiment import ExpFragment
from ndscan.experiment import Fragment
from ndscan.experiment.entry_point import make_fragment_scan_exp
from ndscan.experiment.parameters import FloatParam
from ndscan.experiment.parameters import FloatParamHandle
from ndscan.experiment.result_channels import FloatChannel
from ndscan.experiment.result_channels import IntChannel
from ndscan.experiment.result_channels import OpaqueChannel
from numpy.typing import ArrayLike

from repository.lib.constants import CHAMBER_2_HORIZONTAL_CAMERA_DEFAULTS
from repository.lib.constants import CHAMBER_2_VERTICAL_CAMERA_DEFAULTS


logger = logging.getLogger(__name__)


class AndorCameraControl(Fragment):
    """
    Control the Andor camera and associated shutters / triggers

    For now, just open the shutter and trigger - readout and setup is done manually on the Windows lab PC.
    """

    def build_fragment(self):
        self.setattr_device("core")
        self.core: Core

        self.ttl_trigger: TTLOut = self.get_device("ttl_camera_trigger_andor")
        self.ttl_shutter: TTLOut = self.get_device("ttl_shutter_andor")

        # Kernel variables
        self.debug_enabled = logger.isEnabledFor(logging.DEBUG)

        # %% Kernel invariants
        kernel_invariants = getattr(self, "kernel_invariants", set())
        self.kernel_invariants = kernel_invariants | {
            "debug_enabled",
            "ttl_trigger",
            "ttl_shutter",
        }

    @kernel
    def device_cleanup(self) -> None:
        self.device_cleanup_subfragments()

        # Ensure the camera's protective shutter is closed
        self.core.break_realtime()
        self.ttl_shutter.off()

    @kernel
    def set_shutter(self, state: TBool):
        """
        Open or close the protective shutter

        This will be automatically closed at the end of a sequence if you
        forget, but you should close it immediately after use to avoid damaging
        the camera with lots of light while it's in EM gain mode.
        """
        self.ttl_shutter.set_o(state)

    @kernel
    def trigger(self):
        """
        Trigger an aquisition

        For now, you must manually set up the camera to respond to triggers and
        store the data yourself.

        TODO: Finish Andor fragment
        """
        self.trigger.pulse(1e-6)
