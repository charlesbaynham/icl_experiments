from artiq.experiment import host_only
from artiq.experiment import kernel
from artiq.experiment import TFloat
from artiq.experiment import TList
from ndscan.experiment import *

from repository.lib.fragments.beam_setters import SetBeamsToDefaults
from repository.lib.fragments.magnetic_fields import SetMagneticFieldsQuick


import logging
from typing import *

from artiq.coredevice.ad9910 import AD9910
from artiq.coredevice.core import Core
from artiq.coredevice.dma import CoreDMA
from artiq.experiment import at_mu
from artiq.experiment import delay_mu
from artiq.experiment import kernel
from artiq.experiment import now_mu
from artiq.experiment import portable
from artiq.experiment import TFloat
from artiq.experiment import TInt32
from artiq.experiment import TList
from ndscan.experiment import Fragment
from ndscan.experiment.parameters import FloatParam
from ndscan.experiment.parameters import FloatParamHandle
from numpy import int32
from numpy import int64
from pyaion.fragments.suservo import LibSetSUServoStatic


logger = logging.getLogger(__name__)


class GeneralRampingPhase(Fragment):

    def build_fragment(self, *args, general_setter: Optional[Callable] = None):
        self.setattr_device("core")
        self.core: Core

        self.general_setter = general_setter or self._do_nothing

    @kernel
    def _do_nothing(self, val):
        pass

    @kernel
    def device_setup(self):
        self.general_setter(0.0)

    @kernel
    def do_phase(self):
        pass


class RedRampingPhaseWithFieldsAndSUServoBindings(GeneralRampingPhase):

    def build_fragment(self):
        # Register self.set_fields as the recipient of general ramps
        return super().build_fragment(general_setter=self.do_thing)

    @kernel
    def do_thing(self, val):
        print(val)


class NarrowRedCapturePhase(RedRampingPhaseWithFieldsAndSUServoBindings):
    pass


class NarrowRedCompressionPhase(RedRampingPhaseWithFieldsAndSUServoBindings):
    pass


class RedPhaseUser(ExpFragment):
    def build_fragment(self) -> None:
        self.setattr_device("core")

        self.setattr_fragment(
            "frag1",
            NarrowRedCompressionPhase,
        )
        self.setattr_fragment(
            "frag2",
            NarrowRedCapturePhase,
        )

        self.frag1: NarrowRedCompressionPhase
        self.frag2: NarrowRedCapturePhase

    @kernel
    def run_once(self) -> None:
        self.frag1.do_phase()
        self.frag2.do_phase()


def test_failing_phase_compilation(fragment_precompiler):
    fragment_precompiler(RedPhaseUser)
