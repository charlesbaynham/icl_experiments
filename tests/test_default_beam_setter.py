from artiq.coredevice.core import Core
from artiq.experiment import kernel
from ndscan.experiment import Fragment

from repository.lib.fragments.beam_setters import SetBeamsToDefaults
from repository.lib.models import SUServoedBeam

SAMPLE_BEAM_INFOS = [
    SUServoedBeam(
        "blue_3dmot_axialminus",
        150e6,
        20,
        "suservo_aom_singlepass_461_3DMOT_axialminus",
        servo_enabled=True,
        setpoint=5.0,
    ),
    SUServoedBeam(
        "blue_3dmot_axialplus",
        150e6,
        20,
        "suservo_aom_singlepass_461_3DMOT_axialplus",
        "TTL_shutter_461_3dmot",
        shutter_delay=10e-3,
        servo_enabled=True,
        setpoint=3.2,
    ),
]


class BeamSetterUsedTwice(Fragment):
    def build_fragment(self) -> None:
        self.setattr_device("core")
        self.core: Core

        self.setattr_fragment(
            "all_beam_default_setter_a", SetBeamsToDefaults, SAMPLE_BEAM_INFOS[0]
        )
        self.all_beam_default_setter_a: SetBeamsToDefaults

        self.setattr_fragment(
            "all_beam_default_setter_b", SetBeamsToDefaults, SAMPLE_BEAM_INFOS[1]
        )
        self.all_beam_default_setter_b: SetBeamsToDefaults

    @kernel
    def device_setup(self) -> None:
        self.device_setup_subfragments()

        self.core.break_realtime()

        # Configure and enable the SUServos for all configured beams, and also the delivery beam
        self.all_beam_default_setter_a.turn_on_all(light_enabled=False)
        self.all_beam_default_setter_b.turn_on_all(light_enabled=False)
