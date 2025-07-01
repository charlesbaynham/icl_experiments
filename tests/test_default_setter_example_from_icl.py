from artiq.coredevice.core import Core
from artiq.language import kernel
from ndscan.experiment import ExpFragment

from pyaion.fragments.default_beam_setter import make_set_beams_to_default
from pyaion.models import SUServoedBeam
from pyaion.models import UrukuledBeam

BEAM1 = UrukuledBeam(
    name="beam1",
    frequency=100e6,
    attenuation=0.0,
    urukul_device="ad9912_example_a",
)
BEAM2 = SUServoedBeam(
    name="beam2",
    frequency=100e6,
    attenuation=0.0,
    initial_amplitude=0.05,
    suservo_device="suservo_example_a",
    servo_enabled=True,
    setpoint=1.0,
)

BEAM_INFO_SUSERVO_WITH_SHUTTER = SUServoedBeam(
    "shutter_suservo",
    0.0,
    0.0,
    "suservo_example_b",
    shutter_device="ttl_out_a",
)

BEAM_INFO_AD9910_WITH_SHUTTER = UrukuledBeam(
    "shutter_urukul",
    frequency=100e6,
    amplitude=1.0,
    attenuation=0.0,
    urukul_device="ad9910_example_b",
    shutter_device="ttl_out_b",
)


class TestDefaultSetterWithDualConfig(ExpFragment):
    def build_fragment(self) -> None:
        self.setattr_device("core")
        self.core: Core

        self.setattr_fragment(
            "setter1",
            make_set_beams_to_default(
                urukul_beam_infos=[BEAM1],
            ),
        )

        self.setattr_fragment(
            "setter2",
            make_set_beams_to_default(
                suservo_beam_infos=[BEAM2],
            ),
        )

    @kernel
    def run_once(self) -> None:
        pass


class SimilarButWorks(ExpFragment):
    def build_fragment(self):
        self.setattr_device("core")
        self.core: Core

        self.setattr_fragment(
            "default_setter_a",
            make_set_beams_to_default(
                urukul_beam_infos=[BEAM1],
                suservo_beam_infos=[BEAM_INFO_SUSERVO_WITH_SHUTTER],
            ),
        )
        self.setattr_fragment(
            "default_setter_b",
            make_set_beams_to_default(
                suservo_beam_infos=[BEAM2],
            ),
        )

    @kernel
    def run_once(self) -> None:
        pass


def test_separate_setup(fragment_precompiler):
    fragment_precompiler(TestDefaultSetterWithDualConfig)


def test_combined_setup(fragment_precompiler):
    fragment_precompiler(SimilarButWorks)
