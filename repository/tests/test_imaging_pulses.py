from copy import deepcopy

from artiq.language import delay
from artiq.language import kernel
from ndscan.experiment import ExpFragment
from ndscan.experiment.entry_point import make_fragment_scan_exp

from repository.lib.constants import SUSERVOED_BEAMS
from repository.lib.constants import URUKULED_BEAMS
from repository.lib.fragments.fluorescence_pulse import ImagingFluorescencePulse

MOT_BEAM_NO_SHUTTER = deepcopy(SUSERVOED_BEAMS["blue_3dmot_axialminus"])
MOT_BEAM_NO_SHUTTER.shutter_device = None
MOT_BEAM_WITH_SHUTTER = deepcopy(SUSERVOED_BEAMS["blue_3dmot_axialminus"])
IMAGING_BEAM = deepcopy(URUKULED_BEAMS["blue_imaging_switch"])


class _TestFluorescencePulse(ExpFragment):
    @kernel
    def run_once(self) -> None:
        self.core.break_realtime()
        for _ in range(10):
            delay(1.0)
            self.frag.do_imaging_pulse()


class FluorescencePulseMOTBeamWithoutShutterFrag(_TestFluorescencePulse):
    def build_fragment(self) -> None:
        self.setattr_device("core")

        class _FluorPulse(ImagingFluorescencePulse):
            suservo_beam_infos = [MOT_BEAM_NO_SHUTTER]

        self.setattr_fragment(
            "frag",
            _FluorPulse,
        )
        self.frag: ImagingFluorescencePulse


class FluorescencePulseMOTBeamWithShutterFrag(_TestFluorescencePulse):
    def build_fragment(self) -> None:
        self.setattr_device("core")

        class _FluorPulse(ImagingFluorescencePulse):
            suservo_beam_infos = [MOT_BEAM_WITH_SHUTTER]

        self.setattr_fragment(
            "frag",
            _FluorPulse,
        )


class FluorescencePulseMOTBeamAndImagingWithShutterFrag(_TestFluorescencePulse):
    def build_fragment(self) -> None:
        self.setattr_device("core")

        class _FluorPulse(ImagingFluorescencePulse):
            suservo_beam_infos = [MOT_BEAM_WITH_SHUTTER]
            urukul_beam_infos = [IMAGING_BEAM]

        self.setattr_fragment(
            "frag",
            _FluorPulse,
        )
        self.frag: ImagingFluorescencePulse


class FluorescencePulseSwitchOnlyFrag(_TestFluorescencePulse):
    def build_fragment(self) -> None:
        self.setattr_device("core")

        class _FluorPulse(ImagingFluorescencePulse):
            urukul_beam_infos = [IMAGING_BEAM]

        self.setattr_fragment(
            "frag",
            _FluorPulse,
        )
        self.frag: ImagingFluorescencePulse


FluorescencePulseMOTBeamWithoutShutter = make_fragment_scan_exp(
    FluorescencePulseMOTBeamWithoutShutterFrag
)
FluorescencePulseMOTBeamWithShutter = make_fragment_scan_exp(
    FluorescencePulseMOTBeamWithShutterFrag
)
FluorescencePulseMOTBeamAndImagingWithShutter = make_fragment_scan_exp(
    FluorescencePulseMOTBeamAndImagingWithShutterFrag
)

FluorescencePulseSwitchOnly = make_fragment_scan_exp(FluorescencePulseSwitchOnlyFrag)
