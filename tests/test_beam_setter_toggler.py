import logging
from typing import List

from artiq.coredevice.core import Core
from artiq.experiment import delay
from artiq.experiment import kernel
from ndscan.experiment import ExpFragment
from ndscan.experiment import Fragment
from ndscan.experiment.parameters import FloatParam
from ndscan.experiment.parameters import FloatParamHandle
from pyaion.fragments.beam_setter import ControlBeamsWithoutCoolingAOM
from pyaion.models import SUServoedBeam

import repository.lib.constants as constants
from repository.lib.fragments.beam_setters import SetBeamsToDefaults
from repository.lib.fragments.beam_setters import ToggleListOfBeams
from repository.lib.fragments.suservo import LibSetSUServoStatic

from artiq.experiment import kernel
from ndscan.experiment import ExpFragment
from pyaion.models import SUServoedBeam

from repository.lib.fragments.flourescence_pulse import FlourescencePulse

BEAM_INFO_SUSERVO_NO_SHUTTER = SUServoedBeam(
    "no_shutter_suservo", 0.0, 0.0, "suservo0_ch0"
)


class ToggleSingleSUServoedBeam(ExpFragment):
    @kernel
    def run_once(self) -> None:
        self.core.break_realtime()
        self.all_beam_toggler.turn_on_beams()

    def build_fragment(self) -> None:
        self.setattr_device("core")
        self.core: Core

        self.setattr_fragment(
            "all_beam_toggler", ToggleListOfBeams, [BEAM_INFO_SUSERVO_NO_SHUTTER]
        )
        self.all_beam_toggler: ToggleListOfBeams


def test_all_beam_toggler(fragment_precompiler):
    fragment_precompiler(ToggleSingleSUServoedBeam)
