"""
Tests for the global-parameter symmetric Mach-Zehnder generator and slot-binding
hooks.

The generator (:func:`repository.lib.lmt_sequence.symmetric_mach_zehnder_sequence`) is pure
host code; the binding hooks are pure mappings from a CompiledEvent to a shared
handle attribute name, so both are tested without building an ARTIQ fragment.
"""

import pytest

from repository.lib.lmt_sequence import EVENT_CLEAROUT
from repository.lib.lmt_sequence import EVENT_PULSE
from repository.lib.lmt_sequence import EVENT_SETPOINT
from repository.lib.lmt_sequence import EVENT_WAIT
from repository.lib.lmt_sequence import Beam
from repository.lib.lmt_sequence import Clearout
from repository.lib.lmt_sequence import Pulse
from repository.lib.lmt_sequence import SequenceError
from repository.lib.lmt_sequence import SetPoint
from repository.lib.lmt_sequence import Wait
from repository.lib.lmt_sequence import compile_sequence
from repository.lib.lmt_sequence import symmetric_mach_zehnder_sequence
from repository.lib.physics.lmt_resonance import GROUND


def _make(n_launch, n_recoils, **kwargs):
    return symmetric_mach_zehnder_sequence(
        n_launch=n_launch,
        n_recoils=n_recoils,
        slice_setpoint=0.012,
        slice_rabi_up=1.0 / (2.0 * 380e-6),
        full_setpoint=2.6,
        rabi_up=9e3,
        rabi_down=7e3,
        **kwargs,
    )


@pytest.mark.parametrize("n_launch", range(0, 7))
@pytest.mark.parametrize("n_recoils", range(0, 5))
def test_generated_symmetric_mach_zehnder_closes(n_launch, n_recoils):
    """For any launch/recoil count the interferometer closes to a single
    adjacent momentum pair."""
    sequence = _make(n_launch, n_recoils)
    compiled = compile_sequence(sequence, initial_population={(GROUND, 0)})
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
            expected = 9 + n_launch + (1 if n_launch % 2 == 0 else 0) + 8 * n_recoils
            assert n_events(n_launch, n_recoils) == expected


def test_structure_and_labels():
    sequence = _make(n_launch=4, n_recoils=0)
    compiled = compile_sequence(sequence, initial_population={(GROUND, 0)})
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
        _make(n_launch=3, n_recoils=0), initial_population={(GROUND, 0)}
    )
    clearouts = [e for e in compiled.events if e.kind == EVENT_CLEAROUT]
    assert len(clearouts) == 1  # only the post-slice clearout


def test_dark_waits_reference_global_params():
    compiled = compile_sequence(
        _make(n_launch=2, n_recoils=1), initial_population={(GROUND, 0)}
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


# --- both-arms-excited clearout scrub ------------------------------------


@pytest.mark.parametrize("n_launch", range(0, 7))
@pytest.mark.parametrize("n_recoils", range(0, 5))
def test_clearout_both_excited_leaves_closure_unchanged(n_launch, n_recoils):
    """The inserted clearout/wait pairs are inert in the ideal population walk,
    so the interferometer closes to the same final population as with the flag
    off."""
    off = compile_sequence(
        _make(n_launch, n_recoils), initial_population={(GROUND, 0)}
    ).final_population
    on = compile_sequence(
        _make(n_launch, n_recoils, clearout_both_excited=True),
        initial_population={(GROUND, 0)},
    ).final_population
    assert on == off
    assert len(on) == 2


def test_clearout_both_excited_off_is_byte_for_byte_current():
    """Default off ⇒ the event list is exactly the current one."""
    for n_launch in range(0, 7):
        for n_recoils in range(0, 4):
            assert _make(n_launch, n_recoils, clearout_both_excited=False) == _make(
                n_launch, n_recoils
            )


def test_clearout_both_excited_adds_clearout_wait_pairs():
    """With the flag on and at least one recoil, the sequence gains equal, non-zero
    numbers of clearouts and waits, all bound to the shared clearout_duration."""
    off = compile_sequence(_make(2, 2), initial_population={(GROUND, 0)}).events
    on = compile_sequence(
        _make(2, 2, clearout_both_excited=True), initial_population={(GROUND, 0)}
    ).events

    n_clearouts_off = sum(e.kind == EVENT_CLEAROUT for e in off)
    n_waits_off = sum(e.kind == EVENT_WAIT for e in off)
    n_clearouts_on = sum(e.kind == EVENT_CLEAROUT for e in on)
    n_waits_on = sum(e.kind == EVENT_WAIT for e in on)

    extra_clearouts = n_clearouts_on - n_clearouts_off
    extra_waits = n_waits_on - n_waits_off
    assert extra_clearouts == extra_waits
    assert extra_clearouts > 0

    # Every clearout (existing and inserted) reuses the shared handle; the
    # inserted waits reuse it too (the pre-existing dark waits do not).
    for e in on:
        if e.kind == EVENT_CLEAROUT:
            assert e.duration_param_ref == "clearout_duration"
    on_wait_refs = sorted(e.duration_param_ref for e in on if e.kind == EVENT_WAIT)
    assert on_wait_refs == sorted(
        ["lmt_dark_time_1", "lmt_dark_time_2"] + ["clearout_duration"] * extra_waits
    )


def test_clearout_both_excited_noop_without_recoils():
    """No augmentation steps ⇒ no both-excited window, so the flag inserts
    nothing even when on."""
    assert _make(2, 0, clearout_both_excited=True) == _make(2, 0)


def test_clearout_sits_between_arm_pulses_with_following_wait():
    """Each inserted clearout falls between its step's two arm pulses, and the
    matching wait immediately follows the second pulse."""
    seq = _make(2, 3, clearout_both_excited=True)
    inserted = [
        i
        for i, ev in enumerate(seq)
        if isinstance(ev, Clearout) and ev.label == "both_excited"
    ]
    assert inserted  # at least one for n_recoils >= 1
    for i in inserted:
        assert isinstance(seq[i - 1], Pulse)  # first arm pulse
        assert isinstance(seq[i + 1], Pulse)  # second arm pulse
        assert isinstance(seq[i + 2], Wait)
        assert seq[i + 2].label == "clearout_delay"
        assert seq[i + 2].param == "clearout_duration"


# --- binding hooks -------------------------------------------------------


def _hooks():
    """A mixin instance for calling the pure binding hooks (no build).

    The mixin is abstract (the release-mechanism base leaves
    ``get_doppler_t_ref_mu`` abstract), so a concrete throwaway subclass is
    instantiated via ``object.__new__`` to skip ``build_fragment``.
    """
    from repository.lib.experiment_templates.mixins.lmt_global_params import (
        LMTGlobalParamsSymmetricMachZehnderMixin,
    )

    class _ConcreteHooks(LMTGlobalParamsSymmetricMachZehnderMixin):
        def get_doppler_t_ref_mu(self):
            return 0

    return object.__new__(_ConcreteHooks)


def test_binding_hooks_map_slots_to_global_handles():
    hooks = _hooks()
    compiled = compile_sequence(
        _make(n_launch=2, n_recoils=1), initial_population={(GROUND, 0)}
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

    # Full-intensity up/down pulses bind to the shared per-beam offset/duration
    # (exclude the slice pulse, the only up pulse governed by the slice SetPoint)
    up = next(
        e
        for e in events
        if e.kind == EVENT_PULSE and e.beam_sign > 0 and not hooks._is_slice_pulse(e)
    )
    down = next(
        e
        for e in events
        if e.kind == EVENT_PULSE and e.beam_sign < 0 and not hooks._is_slice_pulse(e)
    )
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


def test_beam_splitters_bind_to_pi2_duration_not_pi():
    """bs1/bs2 (pi/2 events) must bind to the dedicated per-beam pi/2 duration
    handle, not the shared pi duration handle - the bug that fired them as full
    pi pulses in global mode."""
    hooks = _hooks()
    compiled = compile_sequence(
        _make(n_launch=2, n_recoils=1), initial_population={(GROUND, 0)}
    )
    events = compiled.events

    pi2_events = [e for e in events if e.kind == EVENT_PULSE and hooks._is_pi2_pulse(e)]
    # A symmetric Mach-Zehnder has exactly two beam splitters, both down-beam.
    assert len(pi2_events) == 2
    for bs in pi2_events:
        assert bs.beam_sign < 0
        assert hooks.lmt_global_duration_attr(bs) == "lmt_down_pi2_duration"
        assert hooks.lmt_global_duration_attr(bs) != "lmt_down_duration"
        # The offset stays on the shared per-beam handle (resonance is unchanged).
        assert hooks.lmt_global_offset_attr(bs) == "lmt_down_offset"


def test_pi_pulses_still_bind_to_pi_duration():
    """Full pi pulses (launch, mirror) keep the shared per-beam pi duration."""
    hooks = _hooks()
    compiled = compile_sequence(
        _make(n_launch=2, n_recoils=1), initial_population={(GROUND, 0)}
    )
    full_pi = [
        e
        for e in compiled.events
        if e.kind == EVENT_PULSE
        and not hooks._is_slice_pulse(e)
        and not hooks._is_pi2_pulse(e)
    ]
    assert full_pi  # launch + augmentation + mirror pulses
    for e in full_pi:
        expected = "lmt_up_duration" if e.beam_sign > 0 else "lmt_down_duration"
        assert hooks.lmt_global_duration_attr(e) == expected


def test_compiled_pulse_carries_area():
    """The compiler records each pulse's declared area (the discriminator the
    binding hook relies on)."""
    compiled = compile_sequence(
        _make(n_launch=2, n_recoils=1), initial_population={(GROUND, 0)}
    )
    areas = sorted({e.area for e in compiled.events if e.kind == EVENT_PULSE})
    assert areas == [0.5, 1.0]


def test_unexpected_area_pulse_raises_loudly():
    """A full-intensity pulse whose area is neither pi nor pi/2 has no duration
    handle and must raise rather than silently fall through to the pi handle -
    the fall-through that fired the beam splitters as full pi pulses."""
    hooks = _hooks()
    sequence = [
        SetPoint(setpoint=0.012, rabi_up=1e3, label="slice"),  # index 0 (slice)
        SetPoint(setpoint=2.6, rabi_up=9e3, label="full"),  # index 1 (full)
        Pulse(area=0.75, beam=Beam.UP, m=0),  # governed by the full SetPoint
    ]
    compiled = compile_sequence(sequence, initial_population={(GROUND, 0)})
    odd_pulse = compiled.events[2]
    assert not hooks._is_slice_pulse(odd_pulse)
    with pytest.raises(SequenceError):
        hooks.lmt_global_duration_attr(odd_pulse)


def test_global_phase_attr_defaults_to_none():
    """The phase hook defaults to None (NOT raising like the other three), so
    existing global-mode sequences with no Phase events do not crash."""
    hooks = _hooks()
    compiled = compile_sequence(
        _make(n_launch=2, n_recoils=1), initial_population={(GROUND, 0)}
    )
    for event in compiled.events:
        assert hooks.lmt_global_phase_attr(event) is None


def test_per_pulse_mode_is_the_default():
    from repository.lib.experiment_templates.mixins.declarative_lmt import (
        DeclarativeLMTCoreBase,
    )
    from repository.lib.experiment_templates.mixins.lmt_global_params import (
        LMTGlobalParamsSymmetricMachZehnderMixin,
    )

    assert DeclarativeLMTCoreBase.lmt_use_per_pulse_params is True
    assert LMTGlobalParamsSymmetricMachZehnderMixin.lmt_use_per_pulse_params is False
