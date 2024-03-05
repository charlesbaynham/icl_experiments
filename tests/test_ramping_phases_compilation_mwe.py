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

    @portable
    def _calc_step_size(self, start: TFloat, end: TFloat, num: TInt32) -> TFloat:
        return (end - start) / float(num - 1)

    @kernel
    def device_setup(self):
        """
        Records the ramps to DMA.
        Write events are staggered by 8 ns (self.core.ref_multiplier) to use
        only one lane
        """
        self.device_setup_subfragments()

        # Compute grid for writes
        num_points = 1 + int(self.duration // self.time_step)
        time_step_mu = self.core.seconds_to_mu(self.duration / float(num_points))

        # Compute step sizes and initial values for the general ramp
        general_values = [0.0] * len(self.general_setter_param_handles)
        general_steps = [0.0] * len(self.general_setter_param_handles)

        for i in range(len(self.general_setter_param_handles)):
            start_handle = self.general_setter_param_handles[i][0]
            end_handle = self.general_setter_param_handles[i][1]

            general_values[i] = start_handle.get()
            general_steps[i] = self._calc_step_size(
                start_handle.get(), end_handle.get(), num_points
            )

        # Record these ramping parameters into a DMA sequence
        with self.core_dma.record(self.fqn):
            t_this_cycle_mu = now_mu()
            t_one_cycle_mu = int64(self.core.ref_multiplier)

            # Play the ramp
            for i_step in range(num_points):
                at_mu(t_this_cycle_mu)

                # %% Write the general setter steps

                # Do this first since it often writes into the past (e.g. for
                # Zotinos) and we wish to avoid using multiple lanes if possible
                #
                # Unlike with the SUServos and AD9910s, we pass all the new
                # values at once to the setter. It can decide what to do with
                # them
                self.general_setter(general_values)

                # Increment all the values by their steps
                for i in range(len(general_values)):
                    general_values[i] += general_steps[i]

                delay_mu(t_one_cycle_mu)  # Avoid using multiple lanes

                t_this_cycle_mu += time_step_mu

    @kernel
    def do_phase(self):
        pass


class RedRampingPhaseWithFieldsAndSUServoBindings(GeneralRampingPhase):
    # The general ramp here ramps the chamber 2 MOT coils in amps
    general_setter_names = ["chamber_2_mot_current"]
    general_setter_param_options = [{"min": 0, "max": 150, "unit": "A"}]

    def build_fragment(
        self, *args, chamber_2_field_setter: SetMagneticFieldsQuick = None
    ):
        if chamber_2_field_setter is None:
            raise TypeError("You must pass chamber_2_field_setter into build_fragment")
        self.field_setter = chamber_2_field_setter

        # Register self.set_fields as the recipient of general ramps
        return super().build_fragment(*args, general_setter=self.set_fields)

    @kernel
    def set_fields(self, vals: TList(TFloat)):
        self.field_setter.set_mot_gradient(vals[0])


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
            "chamber_2_field_setter",
            SetMagneticFieldsQuick,
        )
        self.chamber_2_field_setter: SetMagneticFieldsQuick

        self.setattr_fragment(
            "frag1",
            NarrowRedCompressionPhase,
            chamber_2_field_setter=self.chamber_2_field_setter,
        )
        self.setattr_fragment(
            "frag2",
            NarrowRedCapturePhase,
            chamber_2_field_setter=self.chamber_2_field_setter,
        )

        self.frag1: NarrowRedCompressionPhase
        self.frag2: NarrowRedCapturePhase

    @kernel
    def run_once(self) -> None:
        self.frag1.do_phase()
        self.frag2.do_phase()


def test_failing_phase_compilation(fragment_precompiler):
    fragment_precompiler(RedPhaseUser)
