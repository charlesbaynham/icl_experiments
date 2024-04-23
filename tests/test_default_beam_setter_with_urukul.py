from artiq.coredevice.core import Core
from artiq.experiment import kernel
from ndscan.experiment import ExpFragment
from pyaion.models import SUServoedBeam
from pyaion.models import UrukuledBeam

from repository.lib.fragments.beams.beam_setters import make_set_beams_to_default
from repository.lib.fragments.beams.beam_setters import SetBeamsToDefaults


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
    "no_shutter_urukul", 100e6, 1.0, 0.0, "urukul2_ch0"
)
BEAM_INFO_URUKUL_WITH_SHUTTER = UrukuledBeam(
    "shutter_urukul",
    100e6,
    0,
    0,
    "urukul2_ch0",
    shutter_device="ttl12",  # This is our first ttl output
)


class SetupSingleSUServoedBeam(ExpFragment):
    def build_fragment(self) -> None:
        self.setattr_device("core")
        self.core: Core

        self.setattr_fragment(
            "default_setter",
            make_set_beams_to_default(
                suservo_beam_infos=[BEAM_INFO_SUSERVO_WITH_SHUTTER]
            ),
        )
        self.default_setter: SetBeamsToDefaults

    @kernel
    def run_once(self):
        self.core.break_realtime()
        self.default_setter.turn_on_all()


class SetupSingleUrukulledBeam(ExpFragment):
    def build_fragment(self) -> None:
        self.setattr_device("core")
        self.core: Core

        self.setattr_fragment(
            "default_setter",
            make_set_beams_to_default(
                urukul_beam_infos=[BEAM_INFO_URUKUL_WITH_SHUTTER]
            ),
        )
        self.default_setter: SetBeamsToDefaults

    @kernel
    def run_once(self):
        self.core.break_realtime()
        self.default_setter.turn_on_all()


class SetupOneOfEach(ExpFragment):
    def build_fragment(self) -> None:
        self.setattr_device("core")
        self.core: Core

        self.setattr_fragment(
            "default_setter",
            make_set_beams_to_default(
                suservo_beam_infos=[BEAM_INFO_SUSERVO_WITH_SHUTTER],
                urukul_beam_infos=[BEAM_INFO_URUKUL_WITH_SHUTTER],
            ),
        )
        self.default_setter: SetBeamsToDefaults

    @kernel
    def run_once(self):
        self.core.break_realtime()
        self.default_setter.turn_on_all()


def test_single_suservo(fragment_precompiler):
    fragment_precompiler(SetupSingleSUServoedBeam)


def test_single_urukul(fragment_precompiler):
    fragment_precompiler(SetupSingleUrukulledBeam)


def test_two_beam_setup(fragment_precompiler):
    fragment_precompiler(SetupOneOfEach)
