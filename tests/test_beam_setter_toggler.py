from artiq.coredevice.core import Core
from artiq.language import kernel
from ndscan.experiment import ExpFragment

# from pyaion.models import SUServoedBeam
from pyaion.models import SUServoedBeam
from pyaion.models import UrukuledBeam

from repository.lib.fragments.beams.toggling_beam_setter import ToggleListOfBeams
from repository.lib.fragments.beams.toggling_beam_setter import (
    make_toggle_list_of_beams,
)

BEAM_INFO_SUSERVO_NO_SHUTTER = SUServoedBeam(
    "no_shutter_suservo", 0.0, 0.0, "suservo0_ch0"
)
BEAM_INFO_SUSERVO_WITH_SHUTTER = SUServoedBeam(
    "shutter_suservo",
    0.0,
    0.0,
    "suservo0_ch0",
    shutter_device="ttl12",  # This is our first ttl output
)

BEAM_INFO_URUKUL_NO_SHUTTER = UrukuledBeam(
    name="no_shutter_urukul",
    frequency=0.0,
    amplitude=0.0,
    attenuation=30.0,
    urukul_device="urukul5_ch0",
)

BEAM_INFO_URUKUL_WITH_SHUTTER = UrukuledBeam(
    name="no_shutter_urukul",
    frequency=0.0,
    amplitude=0.0,
    attenuation=30.0,
    urukul_device="urukul5_ch0",
    shutter_device="ttl12",
)


class ToggleSingleSUServoedBeam(ExpFragment):
    def build_fragment(self) -> None:
        self.setattr_device("core")
        self.core: Core

        self.setattr_fragment(
            "all_beam_toggler",
            make_toggle_list_of_beams([BEAM_INFO_SUSERVO_NO_SHUTTER]),
        )
        self.all_beam_toggler: ToggleListOfBeams

    @kernel
    def run_once(self):
        self.core.break_realtime()
        self.all_beam_toggler.turn_on_beams()


class ToggleOneOfEach(ExpFragment):
    def build_fragment(self) -> None:
        self.setattr_device("core")
        self.core: Core

        self.setattr_fragment(
            "all_beam_toggler",
            make_toggle_list_of_beams(
                [BEAM_INFO_SUSERVO_NO_SHUTTER, BEAM_INFO_SUSERVO_WITH_SHUTTER]
            ),
        )
        self.all_beam_toggler: ToggleListOfBeams

    @kernel
    def run_once(self):
        self.core.break_realtime()
        self.all_beam_toggler.turn_on_beams()


class _DoubleToggler(ToggleListOfBeams):
    default_suservo_beam_infos = [
        BEAM_INFO_SUSERVO_NO_SHUTTER,
        BEAM_INFO_SUSERVO_WITH_SHUTTER,
    ]


class _SingleToggler(ToggleListOfBeams):
    default_suservo_beam_infos = [
        BEAM_INFO_SUSERVO_NO_SHUTTER,
        BEAM_INFO_SUSERVO_WITH_SHUTTER,
    ]


class ToggleMultipleCombos(ExpFragment):
    @kernel
    def run_once(self) -> None:
        self.core.break_realtime()
        self.all_beam_toggler.turn_on_beams()

    def build_fragment(self) -> None:
        self.setattr_device("core")
        self.core: Core

        self.setattr_fragment("both_beam_toggler", _DoubleToggler)
        self.setattr_fragment("one_beam_toggler", _SingleToggler)
        self.both_beam_toggler: ToggleListOfBeams
        self.one_beam_toggler: ToggleListOfBeams

    @kernel
    def run_once(self):
        self.core.break_realtime()
        self.both_beam_toggler.turn_on_beams()
        self.one_beam_toggler.turn_on_beams()


def test_single_beam_toggler(fragment_precompiler):
    fragment_precompiler(ToggleSingleSUServoedBeam)


def test_two_beam_toggler(fragment_precompiler):
    fragment_precompiler(ToggleOneOfEach)


def test_combos(fragment_precompiler):
    fragment_precompiler(ToggleMultipleCombos)
