import logging
import warnings
from typing import List
from typing import Type

from artiq.coredevice.core import Core
from artiq.experiment import kernel
from ndscan.experiment import Fragment
from pyaion.fragments.beam_setter import ControlBeamsWithoutCoolingAOM
from pyaion.fragments.suservo import LibSetSUServoStatic
from pyaion.models import SUServoedBeam
from pyaion.models import UrukuledBeam

from repository.lib.dummy_devices import *


logger = logging.getLogger(__name__)


def make_toggle_list_of_beams(
    beam_infos: List[SUServoedBeam],
) -> Type["ToggleListOfBeams"]:
    """
    Factory function for :class:`~ToggleListOfBeams`. See documentation for
    :meth:`~make_set_beams_to_default` for reasoning.
    """

    class ToggleListOfBeamsCustomised(ToggleListOfBeams):
        default_suservo_beam_infos = beam_infos

    return ToggleListOfBeamsCustomised


class ToggleListOfBeams(Fragment):
    """
    Provides methods to turn on / off a list of beams simultaneously, with or
    without shutters

    Don't use this fragment directly: instead, construct it using
    :meth:`make_toggle_list_of_beams`.

    For each beam_info passed, this Fragment will either use
    :class:`pyaion.fragments.beam_setters.ControlBeamsWithoutCoolingAOM` to open
    / close the shutters in sequence with the toggling to AOM, respecting beam
    delays such that the beams turn on when requested. Or, if no shutter is
    present, this Fragment will simply turn on the beam (with or without the
    SUServo engaged, as defined).
    """

    default_suservo_beam_infos: List[SUServoedBeam] = None  # type: ignore

    def build_fragment(self, default_beam_infos=None):
        if not self.default_suservo_beam_infos and default_beam_infos:
            warnings.warn(
                (
                    "Building ToggleListOfBeams with parameters passed to build_fragment. "
                    "This is not recommended: use the factory function instead"
                ),
                DeprecationWarning,
            )

        self.default_suservo_beam_infos = (
            default_beam_infos or self.default_suservo_beam_infos
        )

        if self.default_suservo_beam_infos is None:
            raise TypeError(
                "You must either create a subclass of SetBeamsToDefaults"
                " or pass in a list of default_beam_infos"
                " - see the documentation"
            )

        self.setattr_device("core")
        self.core: Core

        # Filter our suservoed beams into ones with shutters and ones without
        self.beaminfos_with_shutters: List[SUServoedBeam] = list(
            filter(lambda i: bool(i.shutter_device), self.default_suservo_beam_infos)
        )
        self.beaminfos_without_shutters: List[SUServoedBeam] = list(
            filter(
                lambda i: not bool(i.shutter_device), self.default_suservo_beam_infos
            )
        )

        # Delegate to ControlBeamsWithoutCoolingAOM for the shutter-enabled beams
        self.setattr_fragment(
            "shuttered_beams_setter",
            ControlBeamsWithoutCoolingAOM,
            beam_infos=self.beaminfos_with_shutters,
        )
        self.shuttered_beams_setter: ControlBeamsWithoutCoolingAOM

        # Build a list of LibSetSUServoStatics for the other beams
        self.suservo_frags: List[LibSetSUServoStatic] = []
        for beam in self.beaminfos_without_shutters:
            f = self.setattr_fragment(
                "suservofrag_" + beam.name,
                LibSetSUServoStatic,
                channel=beam.suservo_device,
            )
            self.suservo_frags.append(f)

        # Add a dummy beam / SUServo frag to the list if it's empty - see ARTIQ #1626
        if not self.suservo_frags:
            self.suservo_frags = [_DummySUServoFrag(self)]

            dummy_beaminfo = SUServoedBeam(
                name="dummy",
                frequency=0,
                attenuation=0.0,
                shutter_device="dummy_shutter",
                suservo_device="dummy_suservo",
                shutter_delay=0,
            )
            self.beaminfos_without_shutters.insert(0, dummy_beaminfo)

        # %% Kernel invariants
        kernel_invariants = getattr(self, "kernel_invariants", set())
        self.kernel_invariants = kernel_invariants | {
            "shuttered_beams_setter",
            "suservo_frags",
            "beaminfos_with_shutters",
            "beaminfos_without_shutters",
        }

    @kernel
    def turn_on_beams(self, ignore_shutters=False):
        # Turn on the shuttered beams
        self.shuttered_beams_setter.turn_beams_on(ignore_shutters=ignore_shutters)

        # And the unshuttered beams
        for i in range(len(self.suservo_frags)):
            beam_info = self.beaminfos_without_shutters[i]
            suservo_frag = self.suservo_frags[i]

            suservo_frag.set_channel_state(
                rf_switch_state=True, enable_iir=beam_info.servo_enabled
            )

    @kernel
    def turn_off_beams(self, ignore_shutters=False):
        # Turn off the shuttered beams
        self.shuttered_beams_setter.turn_beams_off(ignore_shutters=ignore_shutters)

        # And the unshuttered beams
        for i in range(len(self.suservo_frags)):
            beam_info = self.beaminfos_without_shutters[i]
            suservo_frag = self.suservo_frags[i]

            suservo_frag.set_channel_state(rf_switch_state=False, enable_iir=False)
