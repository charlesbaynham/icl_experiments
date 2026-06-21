"""
DMA recording + clock-tracking machinery for the post-drop sequence.

:class:`DMAActionsAfterDropMixin` records the
:meth:`~repository.lib.experiment_templates.red_mot_experiment.RedMOTWithExperimentBase.actions_after_drop`
sequence into DMA at the start of each shot (:meth:`DMA_record_hook`) and plays
it back in place of running it live (:meth:`do_experiment_after_red_mot_hook`).
This allows us to:

a) play the post-drop sequence back quickly, and
b) know its timings in advance, so corrected camera-ROI positions can be
   calculated before the shot runs.

Because the sequence is DMA-recorded, no RPCs are allowed inside
``actions_after_drop`` or any hook it calls.

It is mixed into both the red-MOT-drop experiments (in place of the dipole
trap, for when the 1064 nm dipole laser is unavailable) and
:class:`~repository.lib.experiment_templates.dipole_trap_experiment.DipoleTrapWithExperimentBase`.

Timebase
--------

``core_dma.record()`` resets the timeline cursor to zero, so every timestamp
captured *inside* the recording - including everything the
:class:`~repository.lib.fragments.pulse_recorder_and_tracker.PulseDMARecording`
registers - is **recording-relative**. The live time of a recorded event is::

    t_live_mu = t_playback_start_mu + t_recorded_mu

where ``t_playback_start_mu`` is stamped immediately before playback. The
atoms' release time on the live timeline is stamped by :meth:`pre_expansion_hook`
(``run_once`` positions the cursor exactly at red-MOT light-off when that hook
fires). Both anchors are exposed via the :meth:`get_t_release_mu` /
:meth:`get_t_playback_start_mu` portable getters, which the dynamic-ROI imaging
mixins consume.

This mixin **consumes** the ``DMA_record_hook``, ``DMA_initialization_hook``,
``do_experiment_after_red_mot_hook`` and ``pre_expansion_hook`` hooks; in
exchange the post-drop hooks (``post_drop_hook`` / ``launch_hook`` /
``do_experiment_after_drop_hook``) are offered on
:class:`~repository.lib.experiment_templates.red_mot_experiment.RedMOTWithExperimentBase`.
"""

import logging

import numpy as np
from artiq.language import kernel
from artiq.language import now_mu
from artiq.language import portable
from numpy import int64

from repository.lib.experiment_templates.red_mot_experiment import (
    RedMOTWithExperimentBase,
)
from repository.lib.fragments.pulse_recorder_and_tracker import PulseDMARecording

logger = logging.getLogger(__name__)


class DMAActionsAfterDropMixin(RedMOTWithExperimentBase):
    """
    Record :meth:`actions_after_drop` into DMA and play it back, instead of
    running it live, so its timings are known in advance and pulses registered
    during the recording can drive dynamic camera-ROI prediction.

    See the module docstring for the timebase and which hooks are consumed.
    """

    def build_fragment(self):
        super().build_fragment()

        self.setattr_fragment(
            "dma_recording_fragment", PulseDMARecording, outer_self=self
        )
        self.dma_recording_fragment: PulseDMARecording

        # Live-timeline anchors for the recording-relative timestamps captured
        # inside the DMA recording (see module docstring). Stamped each shot
        # by pre_expansion_hook and play_actions_after_drop.
        self.t_atoms_released_mu = int64(0)
        self.t_playback_start_mu = int64(0)

        # Tracking state for clock-pulse frequency recording.
        # Updated by the set_clock_* / start_clock_opll_ramp wrappers defined
        # on the clock-specific bases. Read by PulseDMARecording.register_pulse
        # via outer_self. hasattr-guarded so that a clock base earlier in the
        # build order keeps its values; ClockSpectroscopyBase (later in build
        # order in the usual stacks) still overwrites the defaults with
        # nominal values.
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
    def play_actions_after_drop(self):
        """
        Stamp the playback-start anchor and play back the pre-recorded
        :meth:`actions_after_drop`. Call this where the live sequence would
        otherwise run; the recording was made by :meth:`DMA_record_hook`.

        ``t_playback_start_mu`` is the live-timeline anchor for the
        recording-relative timestamps captured during the recording
        (live time = ``t_playback_start_mu`` + recorded time).
        """
        self.t_playback_start_mu = now_mu()
        self.dma_recording_fragment.playback()

    @kernel
    def do_experiment_after_red_mot_hook(self):
        """Play back the DMA-recorded post-drop sequence."""
        self.play_actions_after_drop()

    @kernel
    def pre_expansion_hook(self):
        """
        Stamp the atom-release time on the live timeline.

        ``run_once`` positions the timeline cursor exactly at red-MOT
        light-off when this hook fires, so ``now_mu()`` here IS the release
        time.
        """
        self.t_atoms_released_mu = now_mu()

    # ------------------------------------------------------------------
    # Timebase accessors for the dynamic-ROI predictor (DynamicROIImagingMixin).
    # ------------------------------------------------------------------

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
        :meth:`play_actions_after_drop`. Recording-relative timestamps map to
        the live timeline as ``t_playback_start_mu + t``. Consumed by the
        dynamic-ROI imaging mixins.
        """
        return self.t_playback_start_mu

    @portable
    def get_t_release_minus_playback_mu(self) -> int64:
        """Release time relative to the DMA playback origin, in machine units.

        Equals ``t_release_mu - t_playback_start_mu``. The dynamic-ROI
        predictor needs only this difference (the absolute playback cursor
        cancels), so it can run in ``before_start_hook`` before either live
        timestamp is stamped. For the red-MOT DMA path the atoms are released
        (light-off) and playback starts ``expansion_time`` later (``run_once``:
        ``at_mu(t_light_off); delay(expansion_time); play_actions_after_drop``),
        so the offset is ``-seconds_to_mu(expansion_time)``.
        """
        return -self.core.seconds_to_mu(self.expansion_time.get())

    # ------------------------------------------------------------------
    # Clock-frequency tracking state lives here (read by
    # PulseDMARecording.register_pulse via a typed outer_self), but the
    # command wrappers that update it are defined on the clock-specific
    # bases next to the devices they drive:
    #   * set_clock_up_dds / set_clock_down_dds -> ClockSpectroscopyBase
    #   * set_clock_opll / start_clock_opll_ramp / stop_clock_opll_ramp
    #     -> ClockOPLLTrackingMixin
    # This keeps clock hardware off non-clock experiments.
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
