import logging
from typing import List
from typing import Type

from artiq.coredevice.core import Core
from artiq.coredevice.ttl import TTLOut
from artiq.language import at_mu
from artiq.language import delay
from artiq.language import kernel
from artiq.language import now_mu
from ndscan.experiment import Fragment
from pyaion.fragments.suservo import LibSetSUServoStatic
from pyaion.fragments.toggle_beams_with_AOM_and_shutter import (
    ControlBeamsWithoutCoolingAOM,
)

# from pyaion.models import SUServoedBeam
from pyaion.models import SUServoedBeam
from pyaion.models import UrukuledBeam

from repository.lib.constants import DELAY_BETWEEN_RTIO_EVENTS
from repository.lib.dummy_devices import DummySUServoFrag
from repository.lib.dummy_devices import DummyTTL

logger = logging.getLogger(__name__)


def make_toggle_list_of_beams(
    suservo_beam_infos: List[SUServoedBeam] = [],
    urukul_beam_infos: List[UrukuledBeam] = [],
) -> Type["ToggleListOfBeams"]:
    """
    Factory function for :class:`~ToggleListOfBeams`. See documentation for
    :meth:`~make_set_beams_to_default` for reasoning.
    """

    class ToggleListOfBeamsCustomised(ToggleListOfBeams):
        default_suservo_beam_infos = suservo_beam_infos
        default_urukul_beam_infos = urukul_beam_infos

    return ToggleListOfBeamsCustomised


class ToggleListOfBeams(Fragment):
    """
    Provides methods to turn on / off a list of beams simultaneously, with or
    without shutters

    Don't use this fragment directly: instead, construct it using
    :meth:`make_toggle_list_of_beams`.

    For each beam_info passed, this Fragment will either use
    :class:`pyaion.fragments.toggle_beams_with_AOM_and_shutters.ControlBeamsWithoutCoolingAOM` to open
    / close the shutters in sequence with the toggling to AOM, respecting beam
    delays such that the beams turn on when requested. Or, if no shutter is
    present, this Fragment will simply turn on the beam (with or without the
    SUServo engaged, as defined).
    """

    default_suservo_beam_infos: List[SUServoedBeam] = None  # type: ignore
    default_urukul_beam_infos: List[UrukuledBeam] = None  # type: ignore

    def build_fragment(self):
        self.default_suservo_beam_infos = self.default_suservo_beam_infos or []
        self.default_urukul_beam_infos = self.default_urukul_beam_infos or []

        if (
            self.default_suservo_beam_infos is []
            and self.default_urukul_beam_infos is []
        ):
            raise TypeError(
                "You must construct this class using the factory function make_toggle_list_of_beams"
                " or by subclassing this class and defining default_suservo_beam_infos or default_urukul_beam_infos"
            )

        self.setattr_device("core")
        self.core: Core

        # Filter our beams into ones with shutters and ones without
        self.suservos_with_shutters: List[SUServoedBeam] = list(
            filter(lambda i: bool(i.shutter_device), self.default_suservo_beam_infos)
        )
        self.suservos_without_shutters: List[SUServoedBeam] = list(
            filter(
                lambda i: not bool(i.shutter_device), self.default_suservo_beam_infos
            )
        )
        self.urukuls_with_shutters: List[UrukuledBeam] = list(
            filter(lambda i: bool(i.shutter_device), self.default_urukul_beam_infos)
        )
        self.urukuls_without_shutters: List[UrukuledBeam] = list(
            filter(lambda i: not bool(i.shutter_device), self.default_urukul_beam_infos)
        )

        if self.urukuls_with_shutters:
            raise NotImplementedError(
                "Toggling urukuls with shutters is not yet supported"
            )

        # Delegate to ControlBeamsWithoutCoolingAOM for the shutter-enabled
        # suservo beams
        self.setattr_fragment(
            "shuttered_beams_setter",
            ControlBeamsWithoutCoolingAOM,
            beam_infos=self.suservos_with_shutters,
        )
        self.shuttered_beams_setter: ControlBeamsWithoutCoolingAOM

        # Build a list of LibSetSUServoStatics for the other suservos
        self.suservo_frags: List[LibSetSUServoStatic] = []
        for beam in self.suservos_without_shutters:
            f = self.setattr_fragment(
                "suservofrag_" + beam.name,
                LibSetSUServoStatic,
                channel=beam.suservo_device,
            )
            self.suservo_frags.append(f)

    def host_setup(self):
        super().host_setup()

        # And get a list of the ttls for the RF switches of the urukulled beams
        self.urukul_ttls: List[TTLOut] = [
            self.get_device(b.urukul_device).sw for b in self.urukuls_without_shutters
        ]

        # Add a dummy beam / SUServo frag to the list if it's empty - see ARTIQ #1626
        if not self.suservo_frags:
            self.suservo_frags = [DummySUServoFrag()]

            dummy_beaminfo = SUServoedBeam(
                name="dummy",
                frequency=0,
                attenuation=0.0,
                shutter_device="dummy_shutter",
                suservo_device="dummy_suservo",
                shutter_delay=0,
            )
            self.suservos_without_shutters.insert(0, dummy_beaminfo)

        if not self.urukul_ttls:
            self.urukul_ttls.append(DummyTTL())

        # %% Kernel invariants
        kernel_invariants = getattr(self, "kernel_invariants", set())
        self.kernel_invariants = kernel_invariants | {
            "shuttered_beams_setter",
            "suservo_frags",
            "suservos_with_shutters",
            "suservos_without_shutters",
        }

    @kernel
    def turn_on_beams(self, ignore_shutters=False):
        """
        Turns on all urukul and suservo beams in the ToggleListOfBeams instance

        Does not advance the timeline.

        Event timings:

        * t < 0: Opens suservo shutters if present at t ~ -20 to -5 ms
        * t ~ 0: Turns on all urukuls and suservos sequentially at t ~ 0 to 100 ns
        """

        _start_mu = now_mu()

        # Turn on the shuttered suservo beams
        self.shuttered_beams_setter.turn_beams_on(ignore_shutters=ignore_shutters)
        delay(
            3
            * DELAY_BETWEEN_RTIO_EVENTS
            * len(self.shuttered_beams_setter.beam_suservos)
        )

        # Turn on the unshuttered suservo beams
        for i in range(len(self.suservo_frags)):
            beam_info = self.suservos_without_shutters[i]
            suservo_frag = self.suservo_frags[i]

            suservo_frag.set_channel_state(
                rf_switch_state=True, enable_iir=beam_info.servo_enabled
            )
            delay(DELAY_BETWEEN_RTIO_EVENTS)

        # And the urukuls
        for ttl in self.urukul_ttls:
            ttl.on()
            delay(DELAY_BETWEEN_RTIO_EVENTS)

        # Reset the timeline
        at_mu(_start_mu)

    @kernel
    def turn_off_beams(self, ignore_shutters=False):
        """
        Turns off all urukul and suservo beams in the ToggleListOfBeams instance

        Does not advance the timeline.

        Event timings:

        * t < 0: Opens suservo shutters if present at t ~ -20 to -5 ms
        * t ~ 0: Turns on all urukuls and suservos sequentially at t ~ 0 to 100 ns
        """
        _start_mu = now_mu()

        # Turn off the shuttered suservo beams
        self.shuttered_beams_setter.turn_beams_off(ignore_shutters=ignore_shutters)
        delay(
            3
            * DELAY_BETWEEN_RTIO_EVENTS
            * len(self.shuttered_beams_setter.beam_suservos)
        )

        # And the unshuttered suservo beams
        for suservo_frag in self.suservo_frags:
            suservo_frag.set_channel_state(rf_switch_state=False, enable_iir=False)
            delay(DELAY_BETWEEN_RTIO_EVENTS)

        # And the urukuls
        for ttl in self.urukul_ttls:
            ttl.off()
            delay(DELAY_BETWEEN_RTIO_EVENTS)

        # Reset the timeline
        at_mu(_start_mu)
