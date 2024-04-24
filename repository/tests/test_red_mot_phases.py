import logging
from typing import *

from artiq.experiment import *
from artiq.experiment import delay
from ndscan.experiment import *

from repository.lib.fragments.magnetic_fields import SetMagneticFieldsQuick
from repository.lib.fragments.ramping_phase import GeneralRampingPhase
from repository.lib.fragments.red_mot.red_beam_controller import RedBeamController
from repository.lib.fragments.red_mot.red_mot_phases import BroadbandRedPhase
from repository.lib.fragments.red_mot.red_mot_phases import NarrowRedCapturePhase
from repository.lib.fragments.red_mot.red_mot_phases import NarrowRedCompressionPhase

logger = logging.getLogger(__name__)


class TestRedPhasesExp(ExpFragment):
    def build_fragment(self) -> None:
        self.setattr_device("core")

        self.setattr_fragment("red_beam_setter", RedBeamController)
        self.red_beam_setter: RedBeamController

        self.setattr_fragment(
            "chamber_2_field_setter",
            SetMagneticFieldsQuick,
        )
        self.chamber_2_field_setter: SetMagneticFieldsQuick

        self.setattr_fragment(
            "frag0",
            BroadbandRedPhase,
            chamber_2_field_setter=self.chamber_2_field_setter,
        )
        self.frag0: GeneralRampingPhase

        self.setattr_fragment(
            "frag1",
            NarrowRedCapturePhase,
            chamber_2_field_setter=self.chamber_2_field_setter,
        )
        self.frag1: GeneralRampingPhase

        self.setattr_fragment(
            "frag2",
            NarrowRedCompressionPhase,
            chamber_2_field_setter=self.chamber_2_field_setter,
        )
        self.frag2: GeneralRampingPhase

    @kernel
    def run_once(self) -> None:
        self.frag0.precalculate_dma_handle()
        self.frag1.precalculate_dma_handle()
        self.frag2.precalculate_dma_handle()

        self.core.break_realtime()
        delay(100e-3)
        self.red_beam_setter.all_beam_default_setter.turn_on_all(light_enabled=True)
        delay(100e-3)

        self.core.break_realtime()
        self.frag0.do_phase()
        self.frag1.do_phase()
        self.frag2.do_phase()

        logger.info("Ramps completed")


TestRedPhases = make_fragment_scan_exp(TestRedPhasesExp)
