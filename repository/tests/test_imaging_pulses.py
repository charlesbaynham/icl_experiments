from artiq.experiment import kernel
from ndscan.experiment import ExpFragment

from repository.lib.models import SUServoedBeam
from repository.lib.fragments.flourescence_pulse import FlourescencePulse


class FlourescencePulseWithoutShutter(ExpFragment):
    @kernel
    def run_once(self) -> None:
        self.core.break_realtime()
        self.frag.do_imaging_pulse()

    def build_fragment(self) -> None:
        self.setattr_device("core")
        self.setattr_fragment(
            "frag",
            FlourescencePulse,
            beam_infos=[
                SUServoedBeam(
                    "blue_3dmot_axialminus",
                    150e6,
                    20,
                    "suservo_aom_singlepass_461_3DMOT_axialminus",
                    servo_enabled=True,
                    setpoint=5.0,
                ),
            ],
        )
        self.frag: FlourescencePulse


# FIXME: I think this fails because I'm attempting polymorphism with ARTIQ via the SetDefaultSettings class
class FlourescencePulseWithShutter(ExpFragment):
    @kernel
    def run_once(self) -> None:
        self.core.break_realtime()
        self.frag.do_imaging_pulse()

    def build_fragment(self) -> None:
        self.setattr_device("core")
        self.setattr_fragment(
            "frag",
            FlourescencePulse,
            beam_infos=[
                SUServoedBeam(
                    "blue_3dmot_axialminus",
                    150e6,
                    20,
                    "suservo_aom_singlepass_461_3DMOT_axialminus",
                    "TTL_shutter_461_3dmot",
                    shutter_delay=10e-3,
                    servo_enabled=True,
                    setpoint=5.0,
                ),
            ],
        )


class FlourescencePulseWithBoth(ExpFragment):
    @kernel
    def run_once(self) -> None:
        self.core.break_realtime()
        self.frag.do_imaging_pulse()

    def build_fragment(self) -> None:
        self.setattr_device("core")
        self.setattr_fragment(
            "frag",
            FlourescencePulse,
            beam_infos=[
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
            ],
        )
        self.frag: FlourescencePulse
