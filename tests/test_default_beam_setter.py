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

SAMPLE_BEAM_INFOS = [
    SUServoedBeam(
        "beam_1",
        150e6,
        20,
        "suservo_aom_singlepass_461_3DMOT_axialminus",
        servo_enabled=True,
        setpoint=5.0,
    ),
    SUServoedBeam(
        "beam_2",
        150e6,
        20,
        "suservo_aom_singlepass_461_3DMOT_axialplus",
        "TTL_shutter_461_3dmot",
        shutter_delay=10e-3,
        servo_enabled=True,
        setpoint=3.2,
    ),
]


class BeamSetterUsedOnce(ExpFragment):
    def build_fragment(self) -> None:
        self.setattr_device("core")
        self.core: Core

        self.setattr_fragment(
            "all_beam_default_setter_a",
            make_set_beams_to_default([SAMPLE_BEAM_INFOS[0]]),
        )
        self.all_beam_default_setter_a: SetBeamsToDefaults

    @kernel
    def device_setup(self) -> None:
        self.device_setup_subfragments()

        self.core.break_realtime()

        # Configure and enable the SUServos for all configured beams, and also the delivery beam
        self.all_beam_default_setter_a.turn_on_all(light_enabled=False)

    def run_once(self) -> None:
        pass


class BeamSetterUsedTwice(ExpFragment):
    def build_fragment(self) -> None:
        self.setattr_device("core")
        self.core: Core

        self.setattr_fragment(
            "all_beam_default_setter_a",
            make_set_beams_to_default([SAMPLE_BEAM_INFOS[0]]),
        )
        self.all_beam_default_setter_a: SetBeamsToDefaults

        self.setattr_fragment(
            "all_beam_default_setter_b",
            make_set_beams_to_default([SAMPLE_BEAM_INFOS[1]]),
        )
        self.all_beam_default_setter_b: SetBeamsToDefaults

    @kernel
    def device_setup(self) -> None:
        self.device_setup_subfragments()

        self.core.break_realtime()

        # Configure and enable the SUServos for all configured beams, and also the delivery beam
        self.all_beam_default_setter_a.turn_on_all(light_enabled=False)
        self.all_beam_default_setter_b.turn_on_all(light_enabled=False)

    def run_once(self) -> None:
        pass


def test_beamsetter_single_use(fragment_precompiler):
    fragment_precompiler(BeamSetterUsedOnce)


def test_beamsetter_double_use(fragment_precompiler):
    fragment_precompiler(BeamSetterUsedTwice)
