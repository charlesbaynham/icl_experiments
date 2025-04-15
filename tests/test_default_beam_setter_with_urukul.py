from abc import ABC
from abc import abstractmethod

from artiq.coredevice.core import Core
from artiq.experiment import kernel
from ndscan.experiment import ExpFragment

from repository.lib.fragments.pyaion_overrides.default_beam_setter_override import (
    SetBeamsToDefaults,
)
from repository.lib.fragments.pyaion_overrides.default_beam_setter_override import (
    make_set_beams_to_default,
)

# from pyaion.models import SUServoedBeam
from repository.lib.fragments.pyaion_overrides.models_override import SUServoedBeam
from repository.lib.fragments.pyaion_overrides.models_override import UrukuledBeam

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

BEAM_INFO_AD9910_NO_SHUTTER = UrukuledBeam(
    "no_shutter_urukul",
    frequency=100e6,
    amplitude=1.0,
    attenuation=0.0,
    urukul_device="urukul5_ch0",  # This is an AD9910
)
BEAM_INFO_AD9910_WITH_SHUTTER = UrukuledBeam(
    "shutter_urukul",
    frequency=100e6,
    amplitude=1.0,
    attenuation=0.0,
    urukul_device="urukul5_ch0",  # This is an AD9910
    shutter_device="ttl12",  # This is our first ttl output
)


BEAM_INFO_AD9912_WITH_SHUTTER = UrukuledBeam(
    "shutter_ad9912",
    frequency=100e6,
    attenuation=0.0,
    urukul_device="urukul2_ch0",  # This is an AD9912
    shutter_device="ttl12",  # This is our first ttl output
)


class _Base(ExpFragment, ABC):
    def build_fragment(self) -> None:
        self.setattr_device("core")
        self.core: Core

        self.add_setter()
        self.default_setter: SetBeamsToDefaults

    @abstractmethod
    def add_setter(self):
        pass

    @kernel
    def run_once(self):
        self.core.break_realtime()
        self.default_setter.turn_on_all()


class SetupSingleSUServoedBeam(_Base):
    def add_setter(self):
        self.setattr_fragment(
            "default_setter",
            make_set_beams_to_default(
                suservo_beam_infos=[BEAM_INFO_SUSERVO_WITH_SHUTTER]
            ),
        )


class SetupSingleUrukulledBeam(_Base):
    def add_setter(self):
        self.setattr_fragment(
            "default_setter",
            make_set_beams_to_default(
                urukul_beam_infos=[BEAM_INFO_AD9910_WITH_SHUTTER]
            ),
        )


class SetupOneOfEach(_Base):
    def add_setter(self):
        self.setattr_fragment(
            "default_setter",
            make_set_beams_to_default(
                suservo_beam_infos=[BEAM_INFO_SUSERVO_WITH_SHUTTER],
                urukul_beam_infos=[BEAM_INFO_AD9910_WITH_SHUTTER],
            ),
        )


class SetupAD9912(_Base):
    def add_setter(self):
        self.setattr_fragment(
            "default_setter",
            make_set_beams_to_default(
                suservo_beam_infos=[],
                urukul_beam_infos=[BEAM_INFO_AD9912_WITH_SHUTTER],
            ),
        )


class SetupAD9910_AD9912_mix(_Base):
    def add_setter(self):
        self.setattr_fragment(
            "default_setter",
            make_set_beams_to_default(
                suservo_beam_infos=[],
                urukul_beam_infos=[
                    BEAM_INFO_AD9912_WITH_SHUTTER,
                    BEAM_INFO_AD9910_WITH_SHUTTER,
                ],
            ),
        )


def test_single_suservo(fragment_precompiler):
    fragment_precompiler(SetupSingleSUServoedBeam)


def test_single_urukul(fragment_precompiler):
    fragment_precompiler(SetupSingleUrukulledBeam)


def test_two_beam_setup(fragment_precompiler):
    fragment_precompiler(SetupOneOfEach)


def test_ad9912(fragment_precompiler):
    fragment_precompiler(SetupAD9912)


def test_ad9910_ad9912(fragment_precompiler):
    fragment_precompiler(SetupAD9910_AD9912_mix)
