"""
Tests for the per-event Rabi handles feeding the AC-Stark correction.

In per-pulse mode each pulse spawns a scannable ``*_rabi`` parameter
defaulting to the SetPoint-declared Rabi; in global mode the kernel keeps
reading the baked ``_lmt_rabi_hz`` floats (a single shared handle cannot
represent mixed up/down Rabis). At defaults both modes must reproduce the old
baked ``-alpha * rabi_declared**2`` exactly.

Pure host-side checks on a bare mixin instance (build skipped), as in
``test_lmt_v0_tether``; ``setattr_param`` is faked to capture the spawned
parameters.
"""

import pytest

from repository.lib import constants
from repository.lib.lmt_sequence import EVENT_PULSE
from repository.lib.lmt_sequence import Beam
from repository.lib.lmt_sequence import Clearout
from repository.lib.lmt_sequence import SetPoint
from repository.lib.lmt_sequence import compile_sequence
from repository.lib.lmt_sequence import ladder
from repository.lib.lmt_sequence import pi
from repository.lib.physics.lmt_resonance import GROUND

SLICE_RABI = 1.0 / (2 * 380e-6)
RABI_UP = 9.1e3
RABI_DOWN = 7.4e3


def _mixed_rabi_sequence():
    sequence = [
        SetPoint(setpoint=0.012, rabi_up=SLICE_RABI, label="slice"),
        pi(Beam.UP, m=0, label="slice"),
        SetPoint(setpoint=2.6, rabi_up=RABI_UP, rabi_down=RABI_DOWN),
        Clearout(),
        *ladder(start_m=1, n=2, first_beam=Beam.DOWN),
    ]
    return compile_sequence(sequence, initial_population={(GROUND, 0)})


class _FakeHandle:
    def __init__(self, value):
        self.value = value

    def get(self):
        return self.value


def _assemble(per_pulse):
    from repository.lib.experiment_templates.mixins.declarative_lmt import (
        DeclarativeLMTBase,
    )

    inst = object.__new__(DeclarativeLMTBase)
    inst.lmt_use_per_pulse_params = per_pulse
    inst._lmt_pad_handle = _FakeHandle(0.0)
    inst._bind_offset_slot = lambda event: None
    inst._bind_duration_slot = lambda event: None
    inst._bind_setpoint_slot = lambda event: None
    inst._bind_phase_slot = lambda event: None

    spawned = {}

    def fake_setattr_param(name, kind, description, **kwargs):
        handle = _FakeHandle(kwargs["default"])
        spawned[name] = handle
        return handle

    inst.setattr_param = fake_setattr_param
    inst._lmt_assemble_event_arrays(_mixed_rabi_sequence())
    return inst, spawned


def test_per_pulse_rabi_params_default_to_declared_rabi():
    inst, spawned = _assemble(per_pulse=True)
    pulse_slots = [
        i for i, kind in enumerate(inst._lmt_event_kind) if kind == EVENT_PULSE
    ]
    assert len(pulse_slots) == 3  # slice + two ladder pulses
    pulses = [e for e in _mixed_rabi_sequence().events if e.kind == EVENT_PULSE]
    assert set(spawned) == {
        e.offset_param.attr_name.removesuffix("_offset") + "_rabi" for e in pulses
    }
    for i in pulse_slots:
        assert inst._lmt_rabi_handles[i].get() == inst._lmt_rabi_hz[i]
    declared = [inst._lmt_rabi_hz[i] for i in pulse_slots]
    assert declared == [SLICE_RABI, RABI_DOWN, RABI_UP]


def test_non_pulse_slots_are_padded():
    inst, _ = _assemble(per_pulse=True)
    for i, kind in enumerate(inst._lmt_event_kind):
        if kind != EVENT_PULSE:
            assert inst._lmt_rabi_handles[i] is inst._lmt_pad_handle
    assert len(inst._lmt_rabi_handles) == inst._lmt_n_events


def test_global_mode_keeps_baked_floats():
    inst, spawned = _assemble(per_pulse=False)
    assert spawned == {}
    assert all(h is inst._lmt_pad_handle for h in inst._lmt_rabi_handles)
    pulse_rabis = [
        inst._lmt_rabi_hz[i]
        for i, kind in enumerate(inst._lmt_event_kind)
        if kind == EVENT_PULSE
    ]
    assert pulse_rabis == [SLICE_RABI, RABI_DOWN, RABI_UP]


@pytest.mark.parametrize(
    "alpha", [constants.DEFAULT_PROBE_STARK_ALPHA_HZ_S2, 2.7e-5, -1.0e-6]
)
def test_stark_at_defaults_equals_old_baked_computation(alpha):
    """Both modes reproduce the pre-handle baked ``-alpha*rabi_declared**2``."""
    per_pulse, _ = _assemble(per_pulse=True)
    global_mode, _ = _assemble(per_pulse=False)
    for i, kind in enumerate(per_pulse._lmt_event_kind):
        if kind != EVENT_PULSE:
            continue
        declared = per_pulse._lmt_rabi_hz[i]
        old_baked = -alpha * declared * declared
        rabi_pp = per_pulse._lmt_rabi_handles[i].get()
        rabi_gl = global_mode._lmt_rabi_hz[i]
        assert -alpha * rabi_pp * rabi_pp == old_baked
        assert -alpha * rabi_gl * rabi_gl == old_baked
