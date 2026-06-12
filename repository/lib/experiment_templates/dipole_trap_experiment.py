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

import numpy as np
from artiq.language import delay
from artiq.language import kernel
from artiq.language import portable
from ndscan.experiment.parameters import FloatParam
from ndscan.experiment.parameters import FloatParamHandle
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
from repository.lib.fragments.checkpoint_fragment import RedMOTCheckpoints
from repository.lib.fragments.dipole_trap.dipole_trap_beam_controller import (
    DipoleBeamController,
)
from repository.lib.fragments.pulse_recorder_and_tracker import PulseDMARecording

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
            default=1550e-6,
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

        self.setattr_fragment(
            "dma_recording_fragment", PulseDMARecording, outer_self=self
        )
        self.dma_recording_fragment: PulseDMARecording

        class _DipoleTrapDMAFrag(RedMOTCheckpoints):
            def build_fragment(self, dma_recording_fragment):
                self.dma_recording_fragment = dma_recording_fragment
                self.kernel_invariants = getattr(self, "kernel_invariants", set())
                self.kernel_invariants.add("dma_recording_fragment")

            @kernel
            def DMA_initialization_checkpoint(self):
                self.DMA_initialization_checkpoint_subfragments()
                self.dma_recording_fragment.DMA_initialization_checkpoint_after_drop()

        self.setattr_fragment(
            "_dipole_trap_dma",
            _DipoleTrapDMAFrag,
            dma_recording_fragment=self.dma_recording_fragment,
        )
        self._dipole_trap_dma: _DipoleTrapDMAFrag  # type: ignore

        # Tracking state for clock-pulse frequency recording.
        # Updated by the set_clock_* / start_clock_opll_ramp wrappers below.
        # Read by PulseDMARecording.register_pulse via outer_self.
        self._tracked_opll_freq = 80e6  # Hz, current static OPLL offset
        self._tracked_opll_ramp_active = False  # whether a DRG ramp is running
        self._tracked_opll_ramp_rate = 0.0  # Hz/s
        self._tracked_opll_ramp_low = 80e6  # Hz, ramp lower bound
        self._tracked_opll_ramp_high = 80e6  # Hz, ramp upper bound
        self._tracked_opll_ramp_wave = np.int32(0)  # 0=triangle, 1=pos saw, 2=neg saw
        self._tracked_opll_ramp_start_mu = np.int64(
            0
        )  # machine-unit timestamp of start_ramp
        # Switch DDS defaults — overridden by ClockSpectroscopyBase to nominal values
        self._tracked_up_switch_freq = 0.0  # Hz, last commanded up-beam switch DDS freq
        self._tracked_down_switch_freq = (
            0.0  # Hz, last commanded down-beam switch DDS freq
        )
        # Delivery AOM tracking — overridden by ClockSpectroscopyBase to nominal values
        self._tracked_delivery_aom_freq = 0.0  # Hz, delivery AOM frequency
        self._tracked_delivery_aom_setpoint = 0.0  # V, delivery AOM SUServo setpoint

    @kernel
    def DMA_record_hook(self):
        self.dma_recording_fragment.record_pulse_sequence()

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

    # ------------------------------------------------------------------
    # Clock-frequency tracking state lives here (read by
    # PulseDMARecording.register_pulse via a typed outer_self), but the
    # command wrappers that update it are defined on the clock-specific
    # bases next to the devices they drive:
    #   * set_clock_up_dds / set_clock_down_dds -> ClockSpectroscopyBase
    #   * set_clock_opll / start_clock_opll_ramp / stop_clock_opll_ramp
    #     -> LMTBase
    # This keeps clock hardware off non-clock dipole experiments.
    # ------------------------------------------------------------------

    @portable
    def _get_opll_instantaneous(self, t_mu: int64) -> float:
        """
        Return the instantaneous OPLL offset frequency (Hz) at timeline
        position t_mu.  For a static setting this is trivial; for an active
        DRG ramp the frequency is extrapolated linearly from the ramp start.

        wave_type 2 (negative sawtooth) ramps down from freq_high;
        all other wave types ramp up from freq_low.
        The ramp spans used for gravity compensation are ~2 MHz wide at
        ~5 kHz/s, so wrapping never occurs within a single experiment shot.
        """
        if not self._tracked_opll_ramp_active:
            return self._tracked_opll_freq
        dt_s = self.core.mu_to_seconds(t_mu - self._tracked_opll_ramp_start_mu)
        if self._tracked_opll_ramp_wave == 2:
            f = self._tracked_opll_ramp_high - self._tracked_opll_ramp_rate * dt_s
            if f < self._tracked_opll_ramp_low:
                return self._tracked_opll_ramp_low
            return f
        else:
            f = self._tracked_opll_ramp_low + self._tracked_opll_ramp_rate * dt_s
            if f > self._tracked_opll_ramp_high:
                return self._tracked_opll_ramp_high
            return f

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
