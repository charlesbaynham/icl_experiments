"""
Tests for the flat pulse-record encoding (``_encode_records_flat``).

These pin the producer side of the ``pulse_record_flat`` / ``pulse_record_offsets``
format that the LMT simulator's ``decode_pulse_record_flat`` consumes. The key
behaviour under test is *per-field dedup*: a phase-only scan re-emits only the
row that changed each shot instead of the whole eight-row record, while the full
sequence still round-trips exactly.

The inline ``_decode`` below is a faithful, minimal mirror of the simulator's
decoder; it exists so this repo can verify the round-trip without depending on
LMT_sim_scratch. The two must stay in lockstep.
"""

import numpy as np
import pytest

from repository.lib.fragments.pulse_recorder_and_tracker import DISABLED_RECORD_SENTINEL
from repository.lib.fragments.pulse_recorder_and_tracker import PARTIAL_RECORD_SENTINEL
from repository.lib.fragments.pulse_recorder_and_tracker import (
    SAME_AS_LAST_RECORD_SENTINEL,
)
from repository.lib.fragments.pulse_recorder_and_tracker import _encode_records_flat

_TOL = 0.5


def _decode(flat, offsets):
    """Minimal mirror of ``lmt_sequence.decode_pulse_record_flat``.

    Returns one entry per record: a list of float rows (the reconstructed full
    record), or ``None`` for a disabled shot.
    """
    flat = np.asarray(flat, dtype=np.float64)
    offsets = np.asarray(offsets, dtype=np.int64)
    out = []
    prev_rows = None
    n = len(offsets)
    for i in range(n):
        start = int(offsets[i])
        end = int(offsets[i + 1]) if i + 1 < n else len(flat)
        record = flat[start:end]

        if len(record) == 1:
            value = float(record[0])
            if abs(value - SAME_AS_LAST_RECORD_SENTINEL) < _TOL:
                assert prev_rows is not None
                out.append([r.copy() for r in prev_rows])
                continue
            if abs(value - DISABLED_RECORD_SENTINEL) < _TOL:
                out.append(None)  # does not update prev_rows
                continue
            raise AssertionError(f"bad length-1 record {value!r}")

        if abs(float(record[0]) - PARTIAL_RECORD_SENTINEL) < _TOL:
            num_entries = int(round(float(record[1])))
            n_rows = int(round(float(record[2])))
            flags = record[3 : 3 + n_rows]
            assert prev_rows is not None
            idx = 3 + n_rows
            rows = []
            for k in range(n_rows):
                if flags[k] > 0.5:
                    rows.append(record[idx : idx + num_entries].copy())
                    idx += num_entries
                else:
                    rows.append(prev_rows[k].copy())
            out.append(rows)
            prev_rows = rows
            continue

        # Full record.
        num_entries = int(round(float(record[0])))
        n_rows = (len(record) - 1) // num_entries
        rows = list(record[1:].reshape(n_rows, num_entries))
        out.append([r.copy() for r in rows])
        prev_rows = rows
    return out


def _rows_equal(a, b):
    return len(a) == len(b) and all(np.allclose(x, y) for x, y in zip(a, b))


def _phase_scan_records(n_shots, num_pulses=20, n_rows=8):
    """A phase-only scan: every field identical shot-to-shot except the last
    (phase) row, which steps each shot."""
    base = [
        [float((row + 1) * (p + 1)) for p in range(num_pulses)] for row in range(n_rows)
    ]
    records = []
    for shot in range(n_shots):
        rec = [row[:] for row in base]
        rec[-1] = [0.1 * shot + p for p in range(num_pulses)]  # phase row varies
        records.append(rec)
    return records


def test_phase_scan_dedups_to_partial_records():
    records = _phase_scan_records(n_shots=10)
    flat, offsets = _encode_records_flat(records, per_field=True)

    # First record is full; the rest are partials carrying only the phase row.
    assert offsets[0] == 0
    assert float(flat[offsets[0]]) not in (
        PARTIAL_RECORD_SENTINEL,
        SAME_AS_LAST_RECORD_SENTINEL,
    )
    for i in range(1, len(records)):
        assert float(flat[offsets[i]]) == PARTIAL_RECORD_SENTINEL

    # A partial record for an 8-row / 20-pulse phase scan stores: marker,
    # num_entries, n_rows, 8 flags, and one changed row of 20 -> 31 floats.
    partial_len = int(offsets[2]) - int(offsets[1])
    assert partial_len == 3 + 8 + 20

    # And it is far smaller than storing the whole record every shot.
    full_only, _ = _encode_records_flat(records, per_field=False)
    assert len(flat) < 0.3 * len(full_only)


def test_phase_scan_round_trips_exactly():
    records = _phase_scan_records(n_shots=10)
    flat, offsets = _encode_records_flat(records, per_field=True)
    decoded = _decode(flat, offsets)
    assert len(decoded) == len(records)
    for original, got in zip(records, decoded):
        assert _rows_equal([np.asarray(r) for r in original], got)


def test_all_static_collapses_to_same_as_last():
    # Nothing changes across shots -> first full, rest single -1.0 sentinels.
    base = _phase_scan_records(n_shots=1)[0]
    records = [[row[:] for row in base] for _ in range(5)]
    flat, offsets = _encode_records_flat(records, per_field=True)
    for i in range(1, len(records)):
        rec_len = (
            int(offsets[i + 1]) - int(offsets[i])
            if i + 1 < len(offsets)
            else len(flat) - int(offsets[i])
        )
        assert rec_len == 1
        assert float(flat[offsets[i]]) == SAME_AS_LAST_RECORD_SENTINEL
    assert _rows_equal([np.asarray(r) for r in base], _decode(flat, offsets)[-1])


def test_all_fields_change_stays_full_record():
    # Every row differs each shot -> a partial would be larger, so store full.
    records = []
    for shot in range(4):
        records.append([[float(shot + row + p) for p in range(5)] for row in range(8)])
    flat, offsets = _encode_records_flat(records, per_field=True)
    for i in range(len(records)):
        assert float(flat[offsets[i]]) not in (
            PARTIAL_RECORD_SENTINEL,
            SAME_AS_LAST_RECORD_SENTINEL,
        )
    decoded = _decode(flat, offsets)
    for original, got in zip(records, decoded):
        assert _rows_equal([np.asarray(r) for r in original], got)


def test_per_field_false_matches_legacy_encoding():
    # The intent record path (per_field=False) must be byte-identical to the
    # original full-record-or-sentinel encoding.
    records = _phase_scan_records(n_shots=3, num_pulses=4, n_rows=7)
    records.insert(1, [[SAME_AS_LAST_RECORD_SENTINEL]])
    records.append([[DISABLED_RECORD_SENTINEL]])

    flat, offsets = _encode_records_flat(records, per_field=False)

    expected = []
    exp_offsets = []
    for record in records:
        exp_offsets.append(len(expected))
        if len(record) == 1 and len(record[0]) == 1:
            expected.append(float(record[0][0]))
        else:
            expected.append(float(len(record[0])))
            for row in record:
                expected.extend(float(x) for x in row)

    assert offsets == exp_offsets
    assert flat == pytest.approx(expected)


def test_disabled_shot_does_not_break_dedup_chain():
    records = _phase_scan_records(n_shots=3)
    records.insert(2, [[DISABLED_RECORD_SENTINEL]])  # storage off for one shot
    flat, offsets = _encode_records_flat(records, per_field=True)
    decoded = _decode(flat, offsets)
    assert decoded[2] is None
    # The shot after the disabled one reuses the last STORED record, not None.
    assert decoded[3] is not None
    assert _rows_equal([np.asarray(r) for r in records[3]], decoded[3])
