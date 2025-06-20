from artiq.coredevice.core import Core
from artiq.language import kernel
from ndscan.experiment import ExpFragment
from pyaion.fragments.default_beam_setter import make_set_beams_to_default
from pyaion.models import SUServoedBeam
from pyaion.models import UrukuledBeam

BEAM1 = UrukuledBeam(
    "beam1",
    frequency=100e6,
    attenuation=13,
    urukul_device="urukul9912_aom_singlepass_461_imaging_switch",
)
BEAM2 = (
    SUServoedBeam(
        "beam2",
        116e6,
        attenuation=20,
        initial_amplitude=0.05,
        suservo_device="suservo_aom_singlepass_461_imaging_delivery",
        servo_enabled=True,
        setpoint=1.5,
    ),
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
