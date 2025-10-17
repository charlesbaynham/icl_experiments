import logging
from typing import *

from artiq.coredevice.core import Core
from artiq.coredevice.ttl import TTLOut
from artiq.language import delay_mu
from artiq.language import kernel
from ndscan.experiment import Fragment
from ndscan.experiment.parameters import BoolParam
from ndscan.experiment.parameters import BoolParamHandle
from numpy import int64
from pyaion.fragments.suservo import LibSetSUServoStatic

# from pyaion.models import SUServoedBeam
from pyaion.models import SUServoedBeam
from pyaion.models import UrukuledBeam

from device_db_config import get_device_db
from repository.lib import constants

logger = logging.getLogger(__name__)


class CloseAllShutters(Fragment):
    """
    Close all shutters for given beams

    This Fragment must be the first subfragment added using
    :meth:`~setattr_subfragment`, otherwise it'll close the shutters durnig
    device_setup after other fragments have acted, potentially changing their
    behaviour.
    """

    ttl_shutters: List[str] = None

    def build_fragment(self) -> None:
        if self.ttl_shutters is None:
            raise NotImplementedError(
                "You must subclass this fragment to specify which shutters you'd like to close"
            )

        if self.ttl_shutters is []:
            raise NotImplementedError("Empty lists are not supported")

        self.setattr_device("core")
        self.core: Core

        self.ttls: List[TTLOut] = []
        for ttl_name in self.ttl_shutters:
            self.ttls.append(self.get_device(ttl_name))

        # %% Kernel invariants and variables
        kernel_invariants = getattr(self, "kernel_invariants", set())
        self.kernel_invariants = kernel_invariants | {"debug_mode", "ttls"}

        self.first_run = True
        self.debug_mode = logger.isEnabledFor(logging.DEBUG)

    @kernel
    def device_setup(self) -> None:
        if self.first_run:
            self.first_run = False

            if self.debug_mode:
                logger.info("Resetting beams")

            self.core.break_realtime()

            for ttl in self.ttls:
                ttl.off()
                delay_mu(int64(self.core.ref_multiplier))

        self.device_setup_subfragments()


class ResetAllBeams(Fragment):
    """
    Turn off all the beams passed

    For all beams, close the shutter and disable the RF switch on the first run
    of the experiment.

    This Fragment must be the first subfragment added using
    :meth:`~setattr_subfragment`, otherwise it'll turn off beams during
    device_setup after other fragments have acted, potentially changing their
    behaviour.
    """

    suservo_beam_infos: Optional[List[SUServoedBeam]] = None
    "List of SUServoedBeam objects to turn off. Must be provided by subclasses"

    urukul_beam_infos: Optional[List[UrukuledBeam]] = None
    "List of UrukuledBeam objects to turn off. Must be provided by subclasses"

    def build_fragment(self) -> None:
        # Default to empty lists if not provided
        if self.suservo_beam_infos is None:
            self.suservo_beam_infos = []
        if self.urukul_beam_infos is None:
            self.urukul_beam_infos = []

        # Check that at least one list is non-empty
        if not self.suservo_beam_infos and not self.urukul_beam_infos:
            raise NotImplementedError(
                "You must subclass this fragment to specify which beams you'd like to turn off"
            )

        if self.suservo_beam_infos is [] and self.urukul_beam_infos is []:
            raise NotImplementedError("Empty lists are not supported")

        self.setattr_device("core")
        self.core: Core

        # Build SUServo channel controllers
        self.suservo_channels: List[LibSetSUServoStatic] = []
        for beam in self.suservo_beam_infos:
            f = self.setattr_fragment(
                f"suservo_{beam.name}", LibSetSUServoStatic, beam.suservo_device
            )
            self.suservo_channels.append(f)  # type: ignore

        self.setattr_param(
            "enabled", BoolParam, description="Enable beam reset", default=True
        )
        self.enabled: BoolParamHandle

        # %% Kernel invariants and variables
        self.first_run = True

        kernel_invariants = getattr(self, "kernel_invariants", set())
        self.kernel_invariants = kernel_invariants | {
            "beam_infos",
            "suservo_channels",
            "all_ttls",
        }

    def host_setup(self):
        # Collect shutters from SUServo beams
        suservo_shutter_ttls: List[TTLOut] = []
        for beam in self.suservo_beam_infos:
            if beam.shutter_device:
                suservo_shutter_ttls.append(self.get_device(beam.shutter_device))

        # Collect shutters from Urukul beams
        urukul_shutter_ttls: List[TTLOut] = []
        for beam in self.urukul_beam_infos:
            if beam.shutter_device:
                urukul_shutter_ttls.append(self.get_device(beam.shutter_device))

        # Get RF switches for Urukul beams (accessed via the .sw attribute)
        urukul_rf_switches: List[TTLOut] = []
        if self.urukul_beam_infos:
            for beam in self.urukul_beam_infos:
                urukul_device = self.get_device(beam.urukul_device)
                urukul_rf_switches.append(urukul_device.sw)

        # Store all TTLs
        self.all_ttls = suservo_shutter_ttls

        return super().host_setup()

    @kernel
    def device_setup(self) -> None:
        if self.enabled.get() and self.first_run:
            self.first_run = False
            self.core.break_realtime()

            # Turn off shutters and Urukul RF switches
            for ttl in self.all_ttls:
                ttl.off()
                delay_mu(int64(self.core.ref_multiplier))

            # Turn off SUServo channels (RF switch and IIR)
            for suservo in self.suservo_channels:
                suservo.set_channel_state(False, False)
                delay_mu(int64(self.core.ref_multiplier))

        self.device_setup_subfragments()


class CloseAllICLShutters(CloseAllShutters):
    ttl_shutters = [
        device_name
        for device_name in get_device_db().keys()
        if "shutter" in device_name
    ]


_suservo_beams = list(constants.SUSERVOED_BEAMS.values())
_suservo_beams = [n for n in _suservo_beams if "lattice" not in n.name]
_urukul_beams = list(constants.URUKULED_BEAMS.values())
_urukul_beams = [n for n in _urukul_beams if "injection" not in n.name]
_urukul_beams = [n for n in _urukul_beams if "blue_xfer_offset" not in n.name]


class ResetAllICLBeams(ResetAllBeams):
    suservo_beam_infos = _suservo_beams
    urukul_beam_infos = _urukul_beams
