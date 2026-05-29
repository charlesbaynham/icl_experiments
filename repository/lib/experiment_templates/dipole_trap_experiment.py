"""
This package provides a template experiment, :class:`~RedMOTWithExperimentBase` .
Unlike other modules, it *does not* provide a Fragment which you should use via
`self.setattr_fragment`. Instead, it defines an :class:`~ExpFragment` which should be
converted into an :class:`~EnvExperiment` using :meth:`~make_fragment_scan_exp`.

The :class:`~ExpFragment`s that this module defines cannot be used without some
customization first. The :meth:`~build_fragment`, :meth:`~device_setup` and
:meth:`~run_once` methods of these :class:`ExpFragment` s contain "hooks" -
methods which can (or sometimes must) be implemented by child classes to alter
the functionality of these experiment. This allows you to reuse this code for
multiple different experiments by implementing child classes which define these
hooks in different ways.

For example, see the documentation of :class:`~RedMOTWithExperimentBase` for the
most basic implementation of hooks.

Mixins
------

This structure of overriding methods allows the use of "mixins". These are
classes which implement various pieces of functionality, which can be selected
from when authoring an experiment.

For example, you might author a mixin that adds imaging with the Andor camera
and another which causes atoms to be trapped in a lattice at the end of the MOT.
Your experiment might then inherit from both of these, to use both features at
the same time::

    from somewhere import AndorImagingMixin, LatticeTrappingMixin


    class MyAndorImagedLatticeExperiment(
        AndorImagingMixin,
        LatticeTrappingMixin,
        RedMOTWithExperimentBase
    ):
        pass

"""

import abc
import logging

from artiq.coredevice.core import Core
from artiq.coredevice.dma import CoreDMA
from artiq.language import delay
from artiq.language import kernel
from artiq.language import now_mu
from ndscan.experiment import Fragment
from ndscan.experiment.parameters import BoolParam
from ndscan.experiment.parameters import BoolParamHandle
from ndscan.experiment.parameters import FloatParam
from ndscan.experiment.parameters import FloatParamHandle
from ndscan.experiment.result_channels import OpaqueChannel
from numpy import int32
from numpy import int64

from repository.lib import constants
from repository.lib.experiment_templates.mixins.constant_lattice import (
    ConstantBeamsMixin,
)
from repository.lib.experiment_templates.mixins.external_triggering import (
    External50HzTriggerMixin,
)
from repository.lib.experiment_templates.red_mot_experiment import (
    RedMOTWithExperimentBase,
)
from repository.lib.fragments.dipole_trap.dipole_trap_beam_controller import (
    DipoleBeamController,
)
from repository.lib.utils import FastIntChecksum

logger = logging.getLogger(__name__)

BUFFER_DEPTH = 300


class DipoleTrapWithExperimentBase(
    External50HzTriggerMixin, ConstantBeamsMixin, RedMOTWithExperimentBase
):
    """
    Run a sequence that makes a red MOT, dipole trap, and then
    does something to it (e.g. a spectroscopy or interferometry sequence) then
    images it.

    Note that this is not a Fragment to be added as a subfragment, nor can it be used as is - you should subclass it and implement
    methods in your child class. You must implement these:

    * `do_experiment_after_dipole_trap_hook`
    * `do_imaging_hook`

    You probably want to implement:

    * `save_data_hook`

    And you may wish to implement other `..._hook` methods.

    Example
    -------

    For a simple implementation see
    :class:`~repository.clock_spectroscopy.clock_spectroscopy.BasicClockSpectroscopyExp`.
    """

    def build_fragment(self):
        super().build_fragment()

        # Hold time in dipole trap - can be negative
        self.setattr_param(
            "dipole_hold_time",
            FloatParam,
            "Time to hold final dipole trap before experiment",
            default=constants.DIPOLE_TRAP_HOLD_TIME,
            unit="us",
        )
        self.dipole_hold_time: FloatParamHandle

        self.setattr_param(
            "dipole_pre_experiment_delay",
            FloatParam,
            "Time to delay experiment after dipole trap or launch",
            default=0.0e-6,
            unit="us",
        )
        self.dipole_pre_experiment_delay: FloatParamHandle

        self.setattr_param(
            "before_launch_delay",
            FloatParam,
            "Time to wait after launch",
            default=0.0,
            unit="us",
        )
        self.before_launch_delay: FloatParamHandle

        # %% Fragments

        self.setattr_fragment("dipole_beam_controller", DipoleBeamController)
        self.dipole_beam_controller: DipoleBeamController

        # Get rid of irrelevant delay after narrowband MOT
        self.override_param("expansion_time", 0)

        class PulseDMARecording(Fragment):
            dma_name = "actions_after_drop"

            def build_fragment(self, outer_self: "DipoleTrapWithExperimentBase"):
                self.outer_self = outer_self

                self.setattr_device("core")
                self.core: Core

                self.setattr_device("core_dma")
                self.core_dma: CoreDMA

                self.setattr_param(
                    "enable_pulse_sequence_storage",
                    BoolParam,
                    description="Store recorded pulse sequences in results",
                    default=True,
                )
                self.enable_pulse_sequence_storage: BoolParamHandle

                self.dma_handle = (int32(0), int64(0), int32(0), False)
                self.dma_handle_valid = False

                # Preallocate a buffer to record pulses
                self._pulse_record_start_times_mu = [int64(0)] * BUFFER_DEPTH
                self._pulse_record_durations_mu = [int64(0)] * BUFFER_DEPTH
                self._pulse_record_directions = [int32(0)] * BUFFER_DEPTH
                self._pulse_record_num_pulses = 0
                self._pulse_record_checksum = int64(0)

                # Add an opaque ResultChannel that is used to store these pulse records
                self.setattr_result(
                    "pulse_record",
                    OpaqueChannel,
                    description="Record of clock pulses",
                    display_hints={"priority": -2},
                )
                self.pulse_record: OpaqueChannel

                # Checksummer object
                self.checksummer = FastIntChecksum(seed=0)

            @kernel
            def device_setup(self):
                self.device_setup_subfragments()

                # Wipe the buffer. The new recording run will overwrite the old data
                self._pulse_record_num_pulses = 0

                # Record the actions_after_drop sequence in DMA
                # FIXME should not recalculate every shot?  maybe?
                with self.core_dma.record(self.dma_name):
                    self.outer_self.actions_after_drop()

                self._save_pulse_sequence_to_dataset()

            @kernel
            def _save_pulse_sequence_to_dataset(self):
                """
                Save the recorded pulse sequence to the OpaqueChannel output

                ARTIQ can't handle dicts etc, so we wrap this into a 2D array.
                This forces us to store directions as int64s which is wasteful,
                but oh well.
                """
                if not self.enable_pulse_sequence_storage.get():
                    self.pulse_record.push(None)
                    return

                pulse_record = [
                    [
                        int64(x)
                        for x in (
                            self._pulse_record_directions[
                                : self._pulse_record_num_pulses
                            ]
                        )
                    ],
                    self._pulse_record_start_times_mu[: self._pulse_record_num_pulses],
                    self._pulse_record_durations_mu[: self._pulse_record_num_pulses],
                ]

                # Calculate a checksum of this pulse record
                checksum = self.checksummer.checksum(
                    [int64(x) for x in pulse_record[0]]
                    + [int64(x) for x in pulse_record[1]]
                    + [int64(x) for x in pulse_record[2]]
                )

                # FIXME
                print("Pulse record checksum:", checksum)

                if checksum != self._pulse_record_checksum:
                    # Record the updated pulse sequence
                    self.pulse_record.push(pulse_record)
                else:
                    # Save None as a sentinal value for "same as last time"
                    self.pulse_record.push(None)

                self._pulse_record_checksum = checksum

            @kernel
            def DMA_initialization_hook_after_drop(self):
                self.dma_handle = self.core_dma.get_handle(self.dma_name)
                self.dma_handle_valid = True

            @kernel
            def playback(self):
                if not self.dma_handle_valid:
                    raise RuntimeError(
                        "DMA buffer handle not set. Did you forget to call DMA_initialization_hook_after_drop?"
                    )
                return self.core_dma.playback_handle(self.dma_handle)

            @kernel
            def register_pulse(self, is_up: bool, duration_s: float):
                """
                Register a clock pulse about to be applied.

                Call this IMMEDIATELY BEFORE turning the clock AOM on so the
                pulse start timestamp and duration are recorded together. Host
                code can then reconstruct whichever effective timing model it
                needs from the full sequence record.
                """

                if self._pulse_record_num_pulses >= BUFFER_DEPTH:
                    raise RuntimeError(
                        "Exceeded maximum number of pulses that can be recorded. Congratulations!!!"
                    )

                duration_mu = self.core.seconds_to_mu(duration_s)

                self._pulse_record_start_times_mu[self._pulse_record_num_pulses] = (
                    now_mu()
                )
                self._pulse_record_durations_mu[self._pulse_record_num_pulses] = (
                    duration_mu
                )
                self._pulse_record_directions[self._pulse_record_num_pulses] = int32(
                    1 if is_up else 0
                )
                self._pulse_record_num_pulses += 1

        self.setattr_fragment(
            "dma_recording_fragment", PulseDMARecording, outer_self=self
        )
        self.dma_recording_fragment: PulseDMARecording

    @kernel
    def DMA_initialization_hook(self):
        self.DMA_initialization_hook_redmot_default()
        self.DMA_initialization_hook_dipole_trap_default()

    @kernel
    def DMA_initialization_hook_dipole_trap_default(self):
        self.dma_recording_fragment.DMA_initialization_hook_after_drop()

    @kernel
    def actions_after_drop(self):
        """
        Split out the parts of the sequence that occur after the atoms are
        dropped so that we can pre-record them in DMA. This allows us to:

        a) playback quickly
        b) know in advance the timings so we can calculate corrected ROI positions

        Note that because this is DMA, we cannot use RPC here
        """

        self.post_dipole_trap_hook()
        delay(self.before_launch_delay.get())
        self.launch_hook()
        delay(self.dipole_pre_experiment_delay.get())
        self.do_experiment_after_dipole_trap_hook()

    @kernel
    def do_experiment_after_red_mot_hook(self):
        self.dipole_trap_loading_hook()
        self.dipole_trap_molasses_hook()
        self.dipole_trap_optical_pumping_hook()
        self.dipole_trap_evaporation_hook()
        self.adiabatic_cooling_hook()
        delay(self.dipole_hold_time.get())
        self.matterwave_collimate_hook()

        # This plays back the pre-recorded version of `actions_after_drop`:
        self.dma_recording_fragment.playback()

    @kernel
    def launch_hook(self):
        """
        Hook for implementation of launching. By default, do nothing
        """

    @kernel
    def dipole_trap_loading_hook(self):
        """
        Hook for implementation of stages in the dipole trap loading stage. By default, turn on the dipole trap beams.
        """
        self.dipole_beam_controller.turn_on_dipole_beams()

    @kernel
    def dipole_trap_molasses_hook(self):
        """
        Hook for implementation of stages in the dipole trap molasses stage. By default, do nothing
        """

    @kernel
    def dipole_trap_optical_pumping_hook(self):
        """
        Hook for implementation of stages after the dipole trap optical pumping stage. By default, do nothing.
        """

    @kernel
    def dipole_trap_evaporation_hook(self):
        """
        Hook for implementation of evaporation in the dipole trap.

        By default, turn off all the red beams to allow holding in dipole trap before experiment
        """
        self.dipole_trap_evaporation_hook_default()

    @kernel
    def post_dipole_trap_hook(self):
        """
        Hook for implementation of stages immediately after the dipole trap is
        released. By default, turn off the dipole trap beams.
        """
        self.post_dipole_trap_hook_default()

    @kernel
    def adiabatic_cooling_hook(self):
        """
        Hook for adiabatic colling.
        By default, do nothing.
        """

    @kernel
    def matterwave_collimate_hook(self):
        """
        Hook for matterwave collimation of the atoms.
        By default, do nothing.
        """

    @kernel
    def register_pulse(self, is_up: bool, duration_s: float):
        """
        Delegate to dma_recording_fragment.register_pulse. `register_pulse` is
        defined on the RedMOTExperimentBase as a no-op, so experiments that use
        clock-pulse mixins can call self.register_pulse unconditionally without
        knowing whether a DMA fragment exists.
        """
        self.dma_recording_fragment.register_pulse(is_up=is_up, duration_s=duration_s)

    @kernel
    def post_dipole_trap_hook_default(self):
        """
        Turn off the dipole trap beams

        Advances the timeline by a few coarse cycles
        """
        self.dipole_beam_controller.turn_off_dipole_beams()
        # maybe add delay
        delay(8e-9)
        self.dipole_beam_controller.turn_off_painter_suservo()
        delay(8e-9)
        self.dipole_beam_controller.turn_off_vertical_up_suservo()

    @kernel
    def dipole_trap_evaporation_hook_default(self):
        """
        Turn off all the red beams to allow holding in dipole trap before experiment

        Advances the timeline by a few coarse cycles
        """
        self.red_mot.red_beam_controller.turn_off_mot_beams(ignore_shutters=True)
        self.red_mot.red_beam_controller.turn_off_spin_pol(ignore_shutters=True)
        self.dipole_beam_controller.turn_off_vertical_up_suservo()

    @abc.abstractmethod
    def do_experiment_after_dipole_trap_hook(self):
        """
        Hook for the implementation of the following cooling stages or
        whatever pulses, executed after the programmed expansion time is
        completed.
        """
        raise NotImplementedError
