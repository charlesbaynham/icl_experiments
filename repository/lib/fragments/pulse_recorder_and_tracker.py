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

import logging

import numpy as np
from artiq.coredevice.core import Core
from artiq.coredevice.dma import CoreDMA
from artiq.language import kernel
from artiq.language import now_mu
from artiq.language import portable
from ndscan.experiment import Fragment
from ndscan.experiment.parameters import BoolParam
from ndscan.experiment.parameters import BoolParamHandle
from numpy import int32
from numpy import int64

from repository.lib.physics.lmt_resonance import M_AUTO
from repository.lib.physics.lmt_resonance import AddressedState
from repository.lib.physics.lmt_resonance import Kind
from repository.lib.physics.lmt_resonance import StateEffect
from repository.lib.utils import FastIntChecksum

logger = logging.getLogger(__name__)

BUFFER_DEPTH = 300

# The intent vocabulary (and the archive schema) is defined in
# repository.lib.physics.lmt_resonance. The Kind/StateEffect/AddressedState IntEnum
# members are int-valued, so the kernel compiler inlines them as compile-time
# integer constants (see tests/test_intenum_kernel_compile.py).

# The pulse record stores physical quantities as floats: times in s,
# frequencies in Hz and the delivery setpoint in V (plus the integer-valued
# direction flag). Start times are stored relative to the atoms' release (the
# dipole drop / red-MOT light-off), not the DMA recording origin; see
# _save_pulse_sequence_to_dataset. They are all stored as float64. The per-shot
# dedup checksum, however, needs integers, so values are scaled by this factor
# before the int64 cast. The scale resolves times to ~1 ns (the RTIO machine-unit
# granularity) so that pulses differing by a single mu are seen as distinct;
# without it sub-microsecond timing changes would collide and be wrongly deduped.
# At this scale frequencies and setpoints keep far-sub-Hz / far-sub-µV
# sensitivity, and the largest scaled field stays well inside int64.
CHECKSUM_SCALE = 1_000_000_000


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
        # Frequencies stored as float Hz; saved as int64 Hz in the OpaqueChannel
        self._pulse_record_opll_freq_hz = [0.0] * BUFFER_DEPTH
        self._pulse_record_switch_freq_hz = [0.0] * BUFFER_DEPTH
        self._pulse_record_delivery_freq_hz = [0.0] * BUFFER_DEPTH
        self._pulse_record_delivery_setpoint = [0.0] * BUFFER_DEPTH
        self._pulse_record_num_pulses = 0
        self._pulse_record_checksum = int64(0)

        # Preallocate the intent stream: one entry per atom-affecting event
        # (clock pulses, clearouts, callbacks) plus dark times (waits),
        # appended at fire time next to the facts. Schema in
        # repository.lib.physics.lmt_resonance.
        self._intent_record_start_times_mu = [int64(0)] * BUFFER_DEPTH
        self._intent_record_durations_mu = [int64(0)] * BUFFER_DEPTH
        self._intent_record_kinds = [int32(0)] * BUFFER_DEPTH
        self._intent_record_state_effects = [int32(0)] * BUFFER_DEPTH
        self._intent_record_addressed_states = [int32(0)] * BUFFER_DEPTH
        self._intent_record_addressed_m = [int32(0)] * BUFFER_DEPTH
        self._intent_record_delta_m = [int32(0)] * BUFFER_DEPTH
        self._intent_record_num_events = 0
        self._intent_record_checksum = int64(0)

        # Checksummer object
        self.checksummer = FastIntChecksum(seed=0)

    def host_setup(self):
        # Create the broadcast datasets for live monitoring. archive=False avoids
        # h5py ragged-array errors; host_cleanup encodes them to flat arrays for archiving.
        self.set_dataset("pulse_record", [], broadcast=True, archive=False)
        self.set_dataset("pulse_intent_record", [], broadcast=True, archive=False)
        super().host_setup()

    @kernel
    def record_pulse_sequence(self):
        # Wipe the buffers; register_pulse() / register_clearout() /
        # register_intent_action() repopulate them during recording
        self._pulse_record_num_pulses = 0
        self._intent_record_num_events = 0
        with self.core_dma.record(self.dma_name):
            self.outer_self.actions_after_drop()
        self._save_pulse_sequence_to_dataset()
        self._save_intent_record_to_dataset()

    @kernel
    def _save_pulse_sequence_to_dataset(self):
        """
        Save the recorded pulse sequence to the pulse_record dataset.

        ARTIQ can't handle dicts etc, so we wrap this into a 2D array. ARTIQ
        also requires that array to be homogeneously typed, so every row is
        stored as float64 in physical units: start times and durations in s
        (converted from machine units via mu_to_seconds), frequencies in Hz and
        the setpoint in V. The direction flag is integer-valued but exactly
        representable as a float.

        Start times are stored **relative to the atoms' release** (the dipole
        drop, or red-MOT light-off): each recording-relative timestamp has the
        drop offset ``get_t_release_minus_playback_mu()`` subtracted before the
        conversion to seconds, so a stored start time is the flight time since
        release (negative for any event preceding the drop). The in-memory
        ``_pulse_record_start_times_mu`` buffers stay recording-relative; only
        this saved representation is rebased.
        """

        SAME_AS_LAST_TIME_SENTINEL = -1.0
        DISABLED_SENTINEL = -2.0

        if not self.enable_pulse_sequence_storage.get():
            self.append_to_dataset("pulse_record", [[DISABLED_SENTINEL]])
            return

        # Recording-relative timestamp of the drop, subtracted to make the
        # stored start times release-relative (see method docstring).
        t_release_mu = self.outer_self.get_t_release_minus_playback_mu()

        directions = [
            float(x)
            for x in self._pulse_record_directions[: self._pulse_record_num_pulses]
        ]
        start_times_s = [
            self.core.mu_to_seconds(x - t_release_mu)
            for x in self._pulse_record_start_times_mu[: self._pulse_record_num_pulses]
        ]
        durations_s = [
            self.core.mu_to_seconds(x)
            for x in self._pulse_record_durations_mu[: self._pulse_record_num_pulses]
        ]
        opll_hz = [
            float(x)
            for x in self._pulse_record_opll_freq_hz[: self._pulse_record_num_pulses]
        ]
        switch_hz = [
            float(x)
            for x in self._pulse_record_switch_freq_hz[: self._pulse_record_num_pulses]
        ]
        delivery_hz = [
            float(x)
            for x in self._pulse_record_delivery_freq_hz[
                : self._pulse_record_num_pulses
            ]
        ]
        delivery_setpoint = [
            float(x)
            for x in self._pulse_record_delivery_setpoint[
                : self._pulse_record_num_pulses
            ]
        ]

        pulse_record = [
            directions,
            start_times_s,
            durations_s,
            opll_hz,
            switch_hz,
            delivery_hz,
            delivery_setpoint,
        ]

        # Calculate a checksum of this pulse record. The checksum needs
        # integers, so each (float) value is scaled before the int64 cast - this
        # keeps it sensitive to sub-unit changes (e.g. a sub-volt setpoint
        # change) that an unscaled int64 cast would hide.
        checksum = int64(0)
        for i in range(7):
            self.checksummer.set_seed(checksum)
            checksum = self.checksummer.checksum(
                [int64(x * CHECKSUM_SCALE) for x in pulse_record[i]]
            )

        if checksum != self._pulse_record_checksum:
            # Record the updated pulse sequence
            self.append_to_dataset("pulse_record", pulse_record)
        else:
            # Save the sentinel value for "same as last time"
            self.append_to_dataset("pulse_record", [[SAME_AS_LAST_TIME_SENTINEL]])

        self._pulse_record_checksum = checksum

    @kernel
    def _save_intent_record_to_dataset(self):
        """
        Save the recorded intent stream to the pulse_intent_record dataset.

        Same conventions as :meth:`_save_pulse_sequence_to_dataset`: a 2D
        float64 array (homogeneous typing for ARTIQ), one row per field, with
        times converted to seconds and the integer-coded fields exactly
        representable as floats. Deduplicated per shot with the same sentinel
        scheme. Start times are release-relative, rebased the same way as the
        pulse facts (the drop offset is subtracted before the seconds cast).
        """

        SAME_AS_LAST_TIME_SENTINEL = -1.0
        DISABLED_SENTINEL = -2.0

        if not self.enable_pulse_sequence_storage.get():
            self.append_to_dataset("pulse_intent_record", [[DISABLED_SENTINEL]])
            return

        # Recording-relative timestamp of the drop, subtracted to make the
        # stored start times release-relative (see _save_pulse_sequence_to_dataset).
        t_release_mu = self.outer_self.get_t_release_minus_playback_mu()

        n = self._intent_record_num_events
        start_times_s = [
            self.core.mu_to_seconds(x - t_release_mu)
            for x in self._intent_record_start_times_mu[:n]
        ]
        durations_s = [
            self.core.mu_to_seconds(x) for x in self._intent_record_durations_mu[:n]
        ]
        kinds = [float(x) for x in self._intent_record_kinds[:n]]
        state_effects = [float(x) for x in self._intent_record_state_effects[:n]]
        addressed_states = [float(x) for x in self._intent_record_addressed_states[:n]]
        addressed_m = [float(x) for x in self._intent_record_addressed_m[:n]]
        delta_m = [float(x) for x in self._intent_record_delta_m[:n]]

        intent_record = [
            kinds,
            start_times_s,
            durations_s,
            state_effects,
            addressed_states,
            addressed_m,
            delta_m,
        ]

        checksum = int64(0)
        for i in range(7):
            self.checksummer.set_seed(checksum)
            checksum = self.checksummer.checksum(
                [int64(x * CHECKSUM_SCALE) for x in intent_record[i]]
            )

        if checksum != self._intent_record_checksum:
            self.append_to_dataset("pulse_intent_record", intent_record)
        else:
            self.append_to_dataset(
                "pulse_intent_record", [[SAME_AS_LAST_TIME_SENTINEL]]
            )

        self._intent_record_checksum = checksum

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

    @portable
    def register_pulse(self, is_up: bool, duration_s: float):
        """
        Register a clock pulse about to be applied, with default intent.

        Call this IMMEDIATELY BEFORE turning the clock AOM on so the
        pulse start timestamp and duration are recorded together. Host
        code can then reconstruct whichever effective timing model it
        needs from the full sequence record.

        The default intent is a resonant pi transfer of whichever pair the
        pulse addresses (resolved from the population walk at prediction
        time), with ``delta_m`` equal to the beam sign. Use
        :meth:`register_pulse_with_intent` to declare anything else.
        """
        self.register_pulse_with_intent(
            is_up=is_up,
            duration_s=duration_s,
            state_effect=StateEffect.FLIP,
            addressed_state=AddressedState.AUTO,
            addressed_m=M_AUTO,
            delta_m=1 if is_up else -1,
        )

    @portable
    def register_pulse_with_intent(
        self,
        is_up: bool,
        duration_s: float,
        state_effect: int32,
        addressed_state: int32,
        addressed_m: int32,
        delta_m: int32,
    ):
        """
        Register a clock pulse about to be applied, declaring its intent.

        The facts (timestamp, duration, beam, tracked frequencies) and the
        intent (what the pulse is meant to do to the atomic populations,
        assumed 100 % efficient) are appended by this single call, so they
        can never misalign - even for conditional or per-shot-varying
        sequences. Field semantics: :mod:`repository.lib.physics.lmt_resonance`.
        """

        if self._pulse_record_num_pulses >= BUFFER_DEPTH:
            raise RuntimeError(
                "Exceeded maximum number of pulses that can be recorded. Congratulations!!!"
            )

        duration_mu = self.core.seconds_to_mu(duration_s)
        t_now_mu = now_mu()

        self._pulse_record_start_times_mu[self._pulse_record_num_pulses] = t_now_mu
        self._pulse_record_durations_mu[self._pulse_record_num_pulses] = duration_mu
        self._pulse_record_directions[self._pulse_record_num_pulses] = int32(
            1 if is_up else 0
        )
        # Report the OPLL frequency at the centre of the pulse
        self._pulse_record_opll_freq_hz[self._pulse_record_num_pulses] = (
            self.outer_self._get_opll_instantaneous(t_now_mu)
            + self.outer_self._get_opll_instantaneous(t_now_mu + duration_mu)
        ) / 2.0
        self._pulse_record_switch_freq_hz[self._pulse_record_num_pulses] = (
            self.outer_self._tracked_up_switch_freq
            if is_up
            else self.outer_self._tracked_down_switch_freq
        )
        self._pulse_record_delivery_freq_hz[self._pulse_record_num_pulses] = (
            self.outer_self._tracked_delivery_aom_freq
        )
        self._pulse_record_delivery_setpoint[self._pulse_record_num_pulses] = (
            self.outer_self._tracked_delivery_aom_setpoint
        )
        self._pulse_record_num_pulses += 1

        self._append_intent(
            t_start_mu=t_now_mu,
            duration_mu=duration_mu,
            kind=Kind.PULSE,
            state_effect=state_effect,
            addressed_state=addressed_state,
            addressed_m=addressed_m,
            delta_m=delta_m,
        )

    @portable
    def register_clearout(self, duration_s: float):
        """
        Register a 461 nm clearout pulse about to be applied.

        Call IMMEDIATELY BEFORE firing the clearout. Records an intent-stream
        entry meaning "remove all ground-state population"; there are no
        pulse facts for clearouts (they are not clock pulses).
        """
        self._append_intent(
            t_start_mu=now_mu(),
            duration_mu=self.core.seconds_to_mu(duration_s),
            kind=Kind.CLEAROUT,
            state_effect=StateEffect.NONE,
            addressed_state=AddressedState.GROUND,
            addressed_m=M_AUTO,
            delta_m=0,
        )

    @portable
    def register_wait(self, duration_s: float):
        """
        Register a dark time about to elapse.

        Call IMMEDIATELY BEFORE the ``delay`` so ``now_mu()`` stamps the start
        of the wait. Records an intent-stream entry that occupies its
        ``[start, start + duration]`` interval but flips no state and imparts no
        momentum, so the sequence-end anchor counts it and the predictor images
        that much later while treating it as pure free flight. Records no pulse
        facts (a wait is not a clock pulse).
        """
        self._append_intent(
            t_start_mu=now_mu(),
            duration_mu=self.core.seconds_to_mu(duration_s),
            kind=Kind.WAIT,
            state_effect=StateEffect.NONE,
            addressed_state=AddressedState.AUTO,
            addressed_m=M_AUTO,
            delta_m=0,
        )

    @portable
    def register_intent_action(
        self,
        duration_s: float,
        state_effect: int32,
        addressed_state: int32,
        addressed_m: int32,
        delta_m: int32,
    ):
        """
        Register one elementary addressed-action of a callback (a shaped pulse
        fired outside the square-pulse path).

        A callback declares its effect as a list of addressed-actions, each
        acting exclusively on one momentum class; this records ONE of them as a
        normal pulse intent row (``Kind.PULSE``) - identical to an ordinary
        pulse, so the trajectory predictor needs no callback-specific logic.
        Like :meth:`register_clearout` it appends only an intent row and records
        NO pulse facts (the shaped pulse is not a tracked square clock pulse).

        Field semantics: :mod:`repository.lib.physics.lmt_resonance`.
        """
        self._append_intent(
            t_start_mu=now_mu(),
            duration_mu=self.core.seconds_to_mu(duration_s),
            kind=Kind.PULSE,
            state_effect=state_effect,
            addressed_state=addressed_state,
            addressed_m=addressed_m,
            delta_m=delta_m,
        )

    @portable
    def _append_intent(
        self,
        t_start_mu: int64,
        duration_mu: int64,
        kind: int32,
        state_effect: int32,
        addressed_state: int32,
        addressed_m: int32,
        delta_m: int32,
    ):
        if self._intent_record_num_events >= BUFFER_DEPTH:
            raise RuntimeError(
                "Exceeded maximum number of intent events that can be recorded."
            )
        n = self._intent_record_num_events
        self._intent_record_start_times_mu[n] = t_start_mu
        self._intent_record_durations_mu[n] = duration_mu
        self._intent_record_kinds[n] = int32(kind)
        self._intent_record_state_effects[n] = int32(state_effect)
        self._intent_record_addressed_states[n] = int32(addressed_state)
        self._intent_record_addressed_m[n] = int32(addressed_m)
        self._intent_record_delta_m[n] = int32(delta_m)
        self._intent_record_num_events += 1

    def host_cleanup(self):
        self._archive_encoded_pulse_records()
        self._archive_encoded_intent_records()
        super().host_cleanup()

    def _archive_encoded_pulse_records(self):
        """Encode accumulated pulse records as flat float64 arrays and archive them.

        Reads records from the ``pulse_record`` broadcast dataset and writes two
        archivable datasets:

        - ``pulse_record_flat``: concatenation of all per-record flat arrays.
        - ``pulse_record_offsets``: starting index in ``pulse_record_flat`` for each
          record, allowing the original records to be reconstructed.

        Each record is encoded as a flat 1D array:

        - Sentinel record (``[[sentinel_value]]``): ``[sentinel_value]`` (length 1)
        - Regular record (7 rows of ``num_pulses`` values each):
          ``[num_pulses, dir_0, …, start_0, …, dur_0, …, opll_0, …, switch_0, …, delivery_0, …, setpoint_0, …]``
          (length ``1 + 7 * num_pulses``)

        All values are stored as float64 in physical units: start times
        (release-relative, as in the broadcast dataset) and durations in s,
        frequencies in Hz and the setpoint in V. The direction and num_pulses
        fields are integer-valued but stored as float64 too.
        """
        self._archive_flat_encoded("pulse_record", "pulse_record")

    def _archive_encoded_intent_records(self):
        """Archive the intent stream with the same flat encoding as the facts.

        Writes ``pulse_intent_record_flat`` / ``pulse_intent_record_offsets``;
        each regular record is ``[num_events, kind_0, …, start_0, …, dur_0, …,
        effect_0, …, addressed_state_0, …, addressed_m_0, …, delta_m_0, …]``.
        Field semantics: :mod:`repository.lib.physics.lmt_resonance`.
        """
        self._archive_flat_encoded("pulse_intent_record", "pulse_intent_record")

    def _archive_flat_encoded(self, source_dataset: str, dest_prefix: str):
        records = self.get_dataset(source_dataset, archive=False)
        if not records:
            return

        flat_data = []
        offsets = []
        current_offset = 0

        for record in records:
            offsets.append(current_offset)
            if len(record) == 1 and len(record[0]) == 1:
                flat_data.append(float(record[0][0]))
                current_offset += 1
            else:
                num_entries = len(record[0])
                flat_data.append(float(num_entries))
                for row in record:
                    flat_data.extend(float(x) for x in row)
                current_offset += 1 + len(record) * num_entries

        self.set_dataset(
            f"{dest_prefix}_flat",
            np.array(flat_data, dtype=np.float64),
            broadcast=False,
            archive=True,
        )
        self.set_dataset(
            f"{dest_prefix}_offsets",
            np.array(offsets, dtype=np.int64),
            broadcast=False,
            archive=True,
        )
