"""
Red-MOT analogue of the dipole-trap DMA experiment structure.

:class:`~RedMOTWithDMAExperimentBase` extends
:class:`~repository.lib.experiment_templates.red_mot_experiment.RedMOTWithExperimentBase`
with the pre-recorded (DMA) post-drop sequence that
:class:`~repository.lib.experiment_templates.dipole_trap_experiment.DipoleTrapWithExperimentBase`
provides for dipole-trap experiments. It exists for periods when the 1064 nm
dipole laser is unavailable: experiments (spectroscopy, LMT, interferometry)
run directly from the red MOT instead of from the dipole trap.

Structure
---------

Everything that happens after the atoms are released from the red MOT is
collected in :meth:`~RedMOTWithDMAExperimentBase.actions_after_drop`, which is
recorded into DMA at the start of each shot
(:meth:`~RedMOTWithDMAExperimentBase.DMA_record_hook`) and played back by
:meth:`~RedMOTWithDMAExperimentBase.do_experiment_after_red_mot_hook`. This
allows us to:

a) play the post-drop sequence back quickly, and
b) know its timings in advance, so corrected camera-ROI positions can be
   calculated before the shot runs.

Because the sequence is DMA-recorded, no RPCs are allowed inside
``actions_after_drop`` or any hook it calls.

Timebase
--------

``core_dma.record()`` resets the timeline cursor to zero, so every timestamp
captured *inside* the recording - including everything the
:class:`~repository.lib.fragments.pulse_recorder_and_tracker.PulseDMARecording`
registers - is **recording-relative**. The live time of a recorded event is::

    t_live_mu = t_playback_start_mu + t_recorded_mu

where ``t_playback_start_mu`` is stamped immediately before playback. The
atoms' release time on the live timeline is stamped by
:meth:`~RedMOTWithDMAExperimentBase.pre_expansion_hook` (``run_once``
positions the cursor exactly at red-MOT light-off when that hook fires).
Both anchors are exposed via the :meth:`get_t_release_mu` /
:meth:`get_t_playback_start_mu` portable getters, which the dynamic-ROI
imaging mixins consume.

Hooks
-----

This base **consumes** (multiple mixins cannot use the same hooks):

* :meth:`~RedMOTWithDMAExperimentBase.DMA_record_hook`
* :meth:`~RedMOTWithDMAExperimentBase.DMA_initialization_hook`
* :meth:`~RedMOTWithDMAExperimentBase.do_experiment_after_red_mot_hook`
* :meth:`~RedMOTWithDMAExperimentBase.pre_expansion_hook`

and **offers** in exchange:

* :meth:`~RedMOTWithDMAExperimentBase.post_drop_hook`
* :meth:`~RedMOTWithDMAExperimentBase.launch_hook`
* :meth:`~RedMOTWithDMAExperimentBase.do_experiment_after_drop_hook`
* :meth:`~RedMOTWithDMAExperimentBase.pre_expansion_hook_dma_extra`
"""

import logging

import numpy as np
from artiq.language import delay
from artiq.language import kernel
from artiq.language import now_mu
from artiq.language import portable
from ndscan.experiment.parameters import FloatParam
from ndscan.experiment.parameters import FloatParamHandle
from numpy import int32
from numpy import int64

from repository.lib.experiment_templates.red_mot_experiment import (
    RedMOTWithExperimentBase,
)
from repository.lib.fragments.pulse_recorder_and_tracker import PulseDMARecording

logger = logging.getLogger(__name__)


class RedMOTWithDMAExperimentBase(RedMOTWithExperimentBase):
    """
    Run a sequence that makes a red MOT, releases the atoms, and then plays a
    pre-recorded (DMA) post-drop sequence on them (e.g. spectroscopy or
    interferometry) before imaging.

    This is the red-MOT analogue of
    :class:`~repository.lib.experiment_templates.dipole_trap_experiment.DipoleTrapWithExperimentBase`,
    for use when the dipole trap is unavailable. The post-drop actions
    (:meth:`actions_after_drop`) are recorded into DMA at the start of each
    shot and played back when the expansion time has elapsed, so their timings
    are known in advance and pulses registered during the recording can drive
    dynamic camera-ROI prediction.

    Subclass it and implement / override hooks; see the module docstring for
    which hooks this base consumes and which it offers. Note that all
    timestamps captured inside the DMA recording are recording-relative; the
    live-timeline anchors are exposed by :meth:`get_t_release_mu` and
    :meth:`get_t_playback_start_mu`.
    """

    def build_fragment(self):
        super().build_fragment()

        self.setattr_param(
            "pre_experiment_delay",
            FloatParam,
            "Delay between post-drop actions and the experiment sequence",
            default=10e-6,
            unit="us",
            min=0.0,
        )
        self.pre_experiment_delay: FloatParamHandle

        self.setattr_fragment(
            "dma_recording_fragment", PulseDMARecording, outer_self=self
        )
        self.dma_recording_fragment: PulseDMARecording

        # Live-timeline anchors for the recording-relative timestamps captured
        # inside the DMA recording (see module docstring). Stamped each shot
        # by pre_expansion_hook and do_experiment_after_red_mot_hook.
        self.t_atoms_released_mu = int64(0)
        self.t_playback_start_mu = int64(0)

        # Tracking state for clock-pulse frequency recording.
        # Updated by the set_clock_* / start_clock_opll_ramp wrappers defined
        # on the clock-specific bases. Read by PulseDMARecording.register_pulse
        # via outer_self. hasattr-guarded so that a clock base earlier in the
        # build order keeps its values; ClockSpectroscopyBase (later in build
        # order in the usual stacks) still overwrites the defaults with
        # nominal values, exactly as in the dipole stack.
        if not hasattr(self, "_tracked_opll_freq"):
            self._tracked_opll_freq = 80e6  # Hz, current static OPLL offset
        if not hasattr(self, "_tracked_opll_ramp_active"):
            self._tracked_opll_ramp_active = False  # whether a DRG ramp is running
        if not hasattr(self, "_tracked_opll_ramp_rate"):
            self._tracked_opll_ramp_rate = 0.0  # Hz/s
        if not hasattr(self, "_tracked_opll_ramp_low"):
            self._tracked_opll_ramp_low = 80e6  # Hz, ramp lower bound
        if not hasattr(self, "_tracked_opll_ramp_high"):
            self._tracked_opll_ramp_high = 80e6  # Hz, ramp upper bound
        if not hasattr(self, "_tracked_opll_ramp_wave"):
            self._tracked_opll_ramp_wave = np.int32(
                0
            )  # 0=triangle, 1=pos saw, 2=neg saw
        if not hasattr(self, "_tracked_opll_ramp_start_mu"):
            self._tracked_opll_ramp_start_mu = np.int64(
                0
            )  # machine-unit timestamp of start_ramp
        # Switch DDS defaults — overridden by ClockSpectroscopyBase to nominal values
        if not hasattr(self, "_tracked_up_switch_freq"):
            self._tracked_up_switch_freq = (
                0.0  # Hz, last commanded up-beam switch DDS freq
            )
        if not hasattr(self, "_tracked_down_switch_freq"):
            self._tracked_down_switch_freq = (
                0.0  # Hz, last commanded down-beam switch DDS freq
            )
        # Delivery AOM tracking — overridden by ClockSpectroscopyBase to nominal values
        if not hasattr(self, "_tracked_delivery_aom_freq"):
            self._tracked_delivery_aom_freq = 0.0  # Hz, delivery AOM frequency
        if not hasattr(self, "_tracked_delivery_aom_setpoint"):
            self._tracked_delivery_aom_setpoint = (
                0.0  # V, delivery AOM SUServo setpoint
            )

    @kernel
    def DMA_record_hook(self):
        self.dma_recording_fragment.record_pulse_sequence()

    @kernel
    def DMA_initialization_hook(self):
        self.DMA_initialization_hook_redmot_default()
        self.dma_recording_fragment.DMA_initialization_hook_after_drop()

    @kernel
    def actions_after_drop(self):
        """
        The post-drop part of the sequence, pre-recorded in DMA by
        :meth:`DMA_record_hook` and played back by
        :meth:`do_experiment_after_red_mot_hook`. This allows us to:

        a) playback quickly
        b) know in advance the timings so we can calculate corrected ROI positions

        Note that because this is DMA, we cannot use RPC here. Also note that
        the recording starts with the timeline cursor at zero, so all
        timestamps captured here are recording-relative (see module docstring).
        """
        # Unconditional marker so the recording is never empty even with all
        # hooks left as defaults (core_dma cannot play back an empty recording)
        delay(1e-6)
        self.post_drop_hook()
        self.launch_hook()
        delay(self.pre_experiment_delay.get())
        self.do_experiment_after_drop_hook()

    @kernel
    def post_drop_hook(self):
        """
        Hook for actions immediately after the atoms are released from the red
        MOT, e.g. velocity slicing. By default, do nothing.
        """

    @kernel
    def launch_hook(self):
        """
        Hook for implementation of launching (e.g. an LMT launch ladder). By
        default, do nothing.
        """

    @kernel
    def do_experiment_after_drop_hook(self):
        """
        Hook for the spectroscopy / interferometry / whatever sequence, fired
        ``pre_experiment_delay`` after the post-drop and launch hooks. By
        default, do nothing.
        """

    @kernel
    def pre_expansion_hook(self):
        """
        Stamp the atom-release time on the live timeline.

        ``run_once`` positions the timeline cursor exactly at red-MOT
        light-off when this hook fires, so ``now_mu()`` here IS the release
        time. This base consumes this hook (the usual convention: multiple
        mixins cannot use the same hook); mixins needing pre-expansion actions
        should override :meth:`pre_expansion_hook_dma_extra` instead.
        """
        self.t_atoms_released_mu = now_mu()
        self.pre_expansion_hook_dma_extra()

    @kernel
    def pre_expansion_hook_dma_extra(self):
        """
        Chainable replacement for ``pre_expansion_hook``, which this base
        consumes. Fired with the cursor at red-MOT light-off; any changes to
        the cursor are ignored (as for ``pre_expansion_hook``). By default,
        do nothing.
        """

    @kernel
    def do_experiment_after_red_mot_hook(self):
        """
        Play back the pre-recorded :meth:`actions_after_drop`.

        :meth:`pre_playback_hook` runs first (live, with whatever slack the
        post-expansion cursor carries) so a subclass can rebuild RTIO slack
        before playback. The playback start time is stamped immediately after
        it: it is the live-timeline anchor for the recording-relative
        timestamps captured during the recording (live time =
        ``t_playback_start_mu`` + recorded time).
        """
        self.pre_playback_hook()
        self.t_playback_start_mu = now_mu()
        self.dma_recording_fragment.playback()

    @kernel
    def pre_playback_hook(self):
        """
        Live actions immediately before the DMA playback, while the timeline
        cursor is still advancing freely. Any delay added here both rebuilds
        RTIO slack for the playback and shifts ``t_playback_start_mu`` later
        (so the recording-relative timebase moves with it). By default, do
        nothing.
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
    def register_pulse_with_intent(
        self,
        is_up: bool,
        duration_s: float,
        state_effect: int32,
        addressed_state: int32,
        addressed_m: int32,
        delta_m: int32,
    ):
        """Delegate to the recording fragment; see :meth:`register_pulse`."""
        self.dma_recording_fragment.register_pulse_with_intent(
            is_up=is_up,
            duration_s=duration_s,
            state_effect=state_effect,
            addressed_state=addressed_state,
            addressed_m=addressed_m,
            delta_m=delta_m,
        )

    @kernel
    def register_clearout(self, duration_s: float):
        """Delegate to the recording fragment; see :meth:`register_pulse`."""
        self.dma_recording_fragment.register_clearout(duration_s=duration_s)

    @kernel
    def register_intent_callback(
        self, duration_s: float, state_effect: int32, delta_m: int32
    ):
        """Delegate to the recording fragment; see :meth:`register_pulse`."""
        self.dma_recording_fragment.register_intent_callback(
            duration_s=duration_s,
            state_effect=state_effect,
            delta_m=delta_m,
        )

    @portable
    def get_t_release_mu(self) -> int64:
        """
        Live-timeline timestamp of the atoms' release from the red MOT
        (red-MOT light-off), stamped each shot by :meth:`pre_expansion_hook`.
        Consumed by the dynamic-ROI imaging mixins.
        """
        return self.t_atoms_released_mu

    @portable
    def get_t_playback_start_mu(self) -> int64:
        """
        Live-timeline timestamp at which playback of the DMA-recorded
        :meth:`actions_after_drop` starts, stamped each shot by
        :meth:`do_experiment_after_red_mot_hook`. Recording-relative
        timestamps map to the live timeline as ``t_playback_start_mu + t``.
        Consumed by the dynamic-ROI imaging mixins.
        """
        return self.t_playback_start_mu

    # ------------------------------------------------------------------
    # Clock-frequency tracking state lives here (read by
    # PulseDMARecording.register_pulse via a typed outer_self), but the
    # command wrappers that update it are defined on the clock-specific
    # bases next to the devices they drive:
    #   * set_clock_up_dds / set_clock_down_dds -> ClockSpectroscopyBase
    #   * set_clock_opll / start_clock_opll_ramp / stop_clock_opll_ramp
    #     -> LMTBase / DeclarativeLMTCoreBase
    # This keeps clock hardware off non-clock red-MOT experiments.
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
