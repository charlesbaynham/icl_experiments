"""
Tests for the global-parameter Mach-Zehnder generator and slot-binding hooks.

The generator (:func:`repository.lib.lmt_sequence.mach_zehnder_sequence`) is pure
host code; the binding hooks are pure mappings from a CompiledEvent to a shared
handle attribute name, so both are tested without building an ARTIQ fragment.
"""

import pytest

from repository.lib.lmt_sequence import EVENT_CLEAROUT
from repository.lib.lmt_sequence import EVENT_PULSE
from repository.lib.lmt_sequence import EVENT_SETPOINT
from repository.lib.lmt_sequence import EVENT_WAIT
from repository.lib.lmt_sequence import compile_sequence
from repository.lib.lmt_sequence import mach_zehnder_sequence


def _make(n_launch, n_recoils):
    return mach_zehnder_sequence(
        n_launch=n_launch,
        n_recoils=n_recoils,
        slice_setpoint=0.012,
        slice_rabi_up=1.0 / (2.0 * 380e-6),
        full_setpoint=2.6,
        rabi_up=9e3,
        rabi_down=7e3,
    )


@pytest.mark.parametrize("n_launch", range(0, 7))
@pytest.mark.parametrize("n_recoils", range(0, 5))
def test_generated_mach_zehnder_closes(n_launch, n_recoils):
    """For any launch/recoil count the interferometer closes to a single
    adjacent momentum pair."""
    sequence = _make(n_launch, n_recoils)
    compiled = compile_sequence(sequence, initial_population={("g", 0)})
    final = compiled.final_population
    assert len(final) == 2
    ms = sorted(m for _, m in final)
    assert ms[1] - ms[0] == 1


def test_event_count_scales_with_counts():
    """Each launch pulse and each recoil adds a fixed number of events."""

    def n_events(n_launch, n_recoils):
        return len(_make(n_launch, n_recoils))

    # 8 events per recoil (separate + rejoin, two arms, two halves)
    assert n_events(4, 1) - n_events(4, 0) == 8
    assert n_events(4, 2) - n_events(4, 1) == 8
    # Closed form: 9 fixed + launch pulses + post-launch clearout (even only)
    # + 8 per recoil
    for n_launch in range(0, 7):
        for n_recoils in range(0, 4):
            expected = (
                9
                + n_launch
                + (1 if n_launch % 2 == 0 else 0)
                + 8 * n_recoils
            )
            assert n_events(n_launch, n_recoils) == expected


def test_structure_and_labels():
    sequence = _make(n_launch=4, n_recoils=0)
    compiled = compile_sequence(sequence, initial_population={("g", 0)})
    kinds = [e.kind for e in compiled.events]
    # slice setpoint, slice pulse, full setpoint, post-slice clearout, launch...
    assert kinds[0] == EVENT_SETPOINT
    assert kinds[1] == EVENT_PULSE
    assert kinds[2] == EVENT_SETPOINT
    assert kinds[3] == EVENT_CLEAROUT
    assert kinds[4:8] == [EVENT_PULSE] * 4  # launch ladder
    assert kinds[8] == EVENT_CLEAROUT  # post-launch (even launch)
    # interferometer: bs1, dark1, mirror, dark2, bs2 (no augmentation)
    assert kinds[9:] == [
        EVENT_PULSE,
        EVENT_WAIT,
        EVENT_PULSE,
        EVENT_WAIT,
        EVENT_PULSE,
    ]
    # The slice pulse is governed by the slice SetPoint (index 0); the launch
    # and interferometer pulses by the full SetPoint (index 2)
    assert compiled.events[1].governing_setpoint_index == 0
    assert compiled.events[4].governing_setpoint_index == 2


def test_odd_launch_skips_post_launch_clearout():
    """An odd launch ends in the ground state, where a post-launch clearout
    would remove the packet, so it is omitted."""
    compiled = compile_sequence(
        _make(n_launch=3, n_recoils=0), initial_population={("g", 0)}
    )
    clearouts = [e for e in compiled.events if e.kind == EVENT_CLEAROUT]
    assert len(clearouts) == 1  # only the post-slice clearout


def test_dark_waits_reference_global_params():
    compiled = compile_sequence(
        _make(n_launch=2, n_recoils=1), initial_population={("g", 0)}
    )
    waits = [e for e in compiled.events if e.kind == EVENT_WAIT]
    assert [w.duration_param_ref for w in waits] == [
        "lmt_dark_time_1",
        "lmt_dark_time_2",
    ]


def test_negative_counts_raise():
    with pytest.raises(ValueError):
        _make(n_launch=-1, n_recoils=0)
    with pytest.raises(ValueError):
        _make(n_launch=2, n_recoils=-1)


# --- binding hooks -------------------------------------------------------


def _hooks():
    """A bare mixin instance for calling the pure binding hooks (no build)."""
    from repository.lib.experiment_templates.mixins.lmt_global_params import (
        LMTGlobalParamsMachZehnderMixin,
    )

    return object.__new__(LMTGlobalParamsMachZehnderMixin)


def test_binding_hooks_map_slots_to_global_handles():
    hooks = _hooks()
    compiled = compile_sequence(
        _make(n_launch=2, n_recoils=1), initial_population={("g", 0)}
    )
    events = compiled.events

    slice_setpoint, slice_pulse, full_setpoint = events[0], events[1], events[2]

    # Set points
    assert hooks.lmt_global_setpoint_attr(slice_setpoint) == "lmt_slice_setpoint"
    assert hooks.lmt_global_setpoint_attr(full_setpoint) == "lmt_full_setpoint"
    assert hooks.lmt_global_setpoint_attr(slice_pulse) is None

    # Slice pulse binds to its own offset/duration
    assert hooks.lmt_global_offset_attr(slice_pulse) == "lmt_slice_offset"
    assert hooks.lmt_global_duration_attr(slice_pulse) == "lmt_slice_duration"

    # Up/down pulses bind to the shared per-beam offset/duration
    up = next(e for e in events if e.kind == EVENT_PULSE and e.beam_sign > 0)
    down = next(e for e in events if e.kind == EVENT_PULSE and e.beam_sign < 0)
    assert hooks.lmt_global_offset_attr(up) == "lmt_up_offset"
    assert hooks.lmt_global_duration_attr(up) == "lmt_up_duration"
    assert hooks.lmt_global_offset_attr(down) == "lmt_down_offset"
    assert hooks.lmt_global_duration_attr(down) == "lmt_down_duration"

    # Waits and clearouts own no offset/duration/set-point slot here
    wait = next(e for e in events if e.kind == EVENT_WAIT)
    clearout = next(e for e in events if e.kind == EVENT_CLEAROUT)
    for inert in (wait, clearout, full_setpoint):
        assert hooks.lmt_global_offset_attr(inert) is None
        assert hooks.lmt_global_duration_attr(inert) is None


def test_per_pulse_mode_is_the_default():
    from repository.lib.experiment_templates.mixins.declarative_lmt import (
        DeclarativeLMTCoreBase,
    )
    from repository.lib.experiment_templates.mixins.lmt_global_params import (
        LMTGlobalParamsMachZehnderMixin,
    )

    assert DeclarativeLMTCoreBase.lmt_use_per_pulse_params is True
    assert LMTGlobalParamsMachZehnderMixin.lmt_use_per_pulse_params is False
