from artiq.experiment import delay
from artiq.experiment import kernel
from ndscan.experiment import ExpFragment
from ndscan.experiment.entry_point import make_fragment_scan_exp
from pyaion.models import SUServoedBeam

from repository.lib.constants import AOM_BEAMS
from repository.lib.fragments.flourescence_pulse import FlourescencePulse

MOT_BEAM_NO_SHUTTER = AOM_BEAMS["blue_3dmot_axialminus"]
MOT_BEAM_NO_SHUTTER.shutter_device = None
MOT_BEAM_WITH_SHUTTER = AOM_BEAMS["blue_3dmot_axialminus"]
IMAGING_BEAM = AOM_BEAMS["blue_imaging_switch"]


class _TestFlourescencePulse(ExpFragment):
    @kernel
    def run_once(self) -> None:
        self.core.break_realtime()
        for _ in range(10):
            delay(1.0)
            self.frag.do_imaging_pulse()


class FlourescencePulseWithoutShutter(_TestFlourescencePulse):
    def build_fragment(self) -> None:
        self.setattr_device("core")
        self.setattr_fragment(
            "frag",
            FlourescencePulse,
            beam_infos=[MOT_BEAM_NO_SHUTTER],
        )
        self.frag: FlourescencePulse


class FlourescencePulseWithShutter(_TestFlourescencePulse):
    def build_fragment(self) -> None:
        self.setattr_device("core")
        self.setattr_fragment(
            "frag",
            FlourescencePulse,
            beam_infos=[MOT_BEAM_WITH_SHUTTER],
        )


class FlourescencePulseWithBoth(_TestFlourescencePulse):
    def build_fragment(self) -> None:
        self.setattr_device("core")
        self.setattr_fragment(
            "frag",
            FlourescencePulse,
            beam_infos=[IMAGING_BEAM, MOT_BEAM_WITH_SHUTTER],
        )
        self.frag: FlourescencePulse


TestFlourescencePulse = make_fragment_scan_exp(FlourescencePulseWithBoth)
