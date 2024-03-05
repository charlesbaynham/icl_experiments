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
    general_setter_names: List[str] = []
    general_setter_param_options: List[Dict] = []
    general_setter_default_starts: List[float] = []
    general_setter_default_ends: List[float] = []

    duration = 100e-3
    time_step = 500e-6

    def build_fragment(self, *args, general_setter: Optional[Callable] = None):
        self.setattr_device("core")
        self.core: Core

        self.setattr_device("core_dma")
        self.core_dma: CoreDMA

        self.general_setter = general_setter or self._do_nothing
        self.general_setter_param_handles = self.build_general_setter_param_handles(
            general_setter
        )

    @kernel
    def _do_nothing(self, num: TList(TFloat)):
        pass

    def build_general_setter_param_handles(self, general_setter):
        setter_was_passed = general_setter is not None

        general_setter_param_handles: List[
            Tuple[
                FloatParamHandle,
                FloatParamHandle,
            ]
        ] = []

        if setter_was_passed:
            for name, options, start, end in zip(
                self.general_setter_names,
                self.general_setter_param_options,
                self.general_setter_default_starts,
                self.general_setter_default_ends,
            ):
                # For each passed parameter to the general setter, make an NDScan parameter
                start_handle = self.setattr_param(
                    f"{name}_start",
                    FloatParam,
                    f"Start value for {name}",
                    default=start,
                    **options,
                )

                end_handle = self.setattr_param(
                    f"{name}_end",
                    FloatParam,
                    f"End value for {name}",
                    default=end,
                    **options,
                )

                general_setter_param_handles.append((start_handle, end_handle))

        else:
            # ARTIQ doesn't like empty lists because it doesn't know what type they are.
            # Rather than work around this, I'll just make a general setter that does nothing.
            # This costs us 8ns per step of wasted time.
            general_setter = self._do_nothing

            # I also need to loop over parameter handles, so I must make a dummy
            # parameter to pass. I'll override it so that it doesn't appear in
            # the parameter listing
            dummy_handle = self.setattr_param(
                "dummy_param", FloatParam, "Dummy parameter - ignore me", default=0.0
            )
            self.override_param("dummy_param", 0.0)

            general_setter_param_handles.append((dummy_handle, dummy_handle))

        return general_setter_param_handles

    @kernel
    def device_setup(self):
        self.general_setter(0.0)

    @kernel
    def do_phase(self):
        pass


class RedRampingPhaseWithFieldsAndSUServoBindings(GeneralRampingPhase):
    # The general ramp here ramps the chamber 2 MOT coils in amps
    general_setter_names = ["chamber_2_mot_current"]
    general_setter_param_options = [{"min": 0, "max": 150, "unit": "A"}]

    def build_fragment(self):
        # Register self.set_fields as the recipient of general ramps
        return super().build_fragment(general_setter=self.do_thing)

    @kernel
    def do_thing(self, val):
        print(val)


class NarrowRedCapturePhase(RedRampingPhaseWithFieldsAndSUServoBindings):
    duration_default = 50e-3

    # Chamber 2 MOT coils in amps
    general_setter_default_starts = [5.0]
    general_setter_default_ends = [1.0]


class NarrowRedCompressionPhase(RedRampingPhaseWithFieldsAndSUServoBindings):
    duration_default = 100e-3

    # Chamber 2 MOT coils in amps
    general_setter_default_starts = [1.0]
    general_setter_default_ends = [1.0]


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
