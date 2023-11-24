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
from artiq.experiment import delay
from artiq.experiment import delay_mu
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

from repository.lib import constants

logger = logging.getLogger(__name__)

ANDOR_TRIGGER_LENGTH = 1.0e-6


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

        # %% Params

        self.setattr_param(
            "shutter_delay",
            FloatParam,
            "Time to allow for shutter to open before imaging",
            default=constants.ANDOR_CAMERA_SHUTTER_OPEN_TIME,
            unit="ms",
            min=0.0,
        )
        self.shutter_delay: FloatParamHandle

        # %% Kernel variables
        self.debug_enabled = logger.isEnabledFor(logging.DEBUG)

        # %% Kernel invariants
        kernel_invariants = getattr(self, "kernel_invariants", set())
        self.kernel_invariants = kernel_invariants | {
            "debug_enabled",
            "ttl_trigger",
            "ttl_shutter",
        }

    @kernel
    def device_setup(self) -> None:
        self.device_setup_subfragments()

        self.core.break_realtime()

        self.ttl_shutter.off()
        delay(self.core.coarse_ref_period)
        self.ttl_trigger.off()
        delay(self.core.coarse_ref_period)
        self.ttl_shutter.output()
        delay(self.core.coarse_ref_period)
        self.ttl_trigger.output()

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
    def trigger(self, control_shutter=False):
        """
        Trigger an aquisition

        For now, you must manually set up the camera to respond to triggers and
        store the data yourself.

        If control_shutter == True, open the shutter <shutter_delay> in advance and then close if afterwards.

        TODO: Finish Andor fragment to fully control camera, including readout
        """

        if control_shutter:
            shutter_delay_mu = self.core.seconds_to_mu(self.shutter_delay.get())
            delay_mu(-shutter_delay_mu)
            self.ttl_shutter.on()
            delay_mu(shutter_delay_mu)

        self.ttl_trigger.pulse(ANDOR_TRIGGER_LENGTH)

        if control_shutter:
            self.ttl_shutter.off()
