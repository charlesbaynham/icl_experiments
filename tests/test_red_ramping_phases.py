from typing import *

from artiq.experiment import *
from ndscan.experiment import *
from pyaion.fragments.default_beam_setter import SetBeamsToDefaults
from pyaion.fragments.default_beam_setter import make_set_beams_to_default

from repository.lib import constants
from repository.lib.fragments.magnetic_fields import SetMagneticFieldsQuick
from repository.lib.fragments.red_mot.red_mot_phases import BroadbandRedPhase
from repository.lib.fragments.red_mot.red_mot_phases import NarrowRedCapturePhase
from repository.lib.fragments.red_mot.red_mot_phases import NarrowRedCompressionPhase
from repository.lib.fragments.red_mot.red_mot_phases import (
    RedRampingPhaseWithFieldsAndSUServoBindings,
)


def build_phase_user(phase: Type[RedRampingPhaseWithFieldsAndSUServoBindings]):
    class Ramper(ExpFragment):
        def build_fragment(self) -> None:
            self.setattr_device("core")

            self.setattr_fragment(
                "beam_setter",
                make_set_beams_to_default(
                    [
                        constants.SUSERVOED_BEAMS["red_mot_diagonal"],
                        constants.SUSERVOED_BEAMS["red_mot_sigmaplus"],
                        constants.SUSERVOED_BEAMS["red_mot_sigmaminus"],
                        constants.SUSERVOED_BEAMS["red_up"],
                    ],
                    name="beam_setter",
                ),
            )
            self.beam_setter: SetBeamsToDefaults

            self.setattr_fragment(
                "chamber_2_field_setter",
                SetMagneticFieldsQuick,
            )
            self.chamber_2_field_setter: SetMagneticFieldsQuick

            self.setattr_fragment("frag1", phase)
            self.frag1: RedRampingPhaseWithFieldsAndSUServoBindings

            self.frag1.bind_suservo_setpoint_params_to_default_beam_setter(
                self.beam_setter
            )

        @kernel
        def run_once(self) -> None:
            self.frag1.do_phase()

    Ramper.__name__ = phase.__name__ + "_ramper"
    return Ramper


def test_NarrowRedCapturePhase(fragment_precompiler):
    fragment_precompiler(build_phase_user(NarrowRedCapturePhase))


def test_NarrowRedCompressionPhase(fragment_precompiler):
    fragment_precompiler(build_phase_user(NarrowRedCompressionPhase))


def test_BroadbandRedPhase(fragment_precompiler):
    fragment_precompiler(build_phase_user(BroadbandRedPhase))
