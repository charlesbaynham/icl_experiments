"""
Tests for the recorded-intent vocabulary: enum coercion/validation and the
shared ``IntentEvent.addresses_pair`` predicate used by both the dynamic-ROI
predictor and the spacetime diagram.

The vocabulary lives in :mod:`repository.lib.physics.lmt_resonance`.
"""

import pytest

from repository.lib.physics.lmt_resonance import EXCITED
from repository.lib.physics.lmt_resonance import GROUND
from repository.lib.physics.lmt_resonance import M_AUTO
from repository.lib.physics.lmt_resonance import AddressedState
from repository.lib.physics.lmt_resonance import IntentEvent
from repository.lib.physics.lmt_resonance import Kind
from repository.lib.physics.lmt_resonance import StateEffect


def _event(
    *,
    kind=Kind.PULSE,
    state_effect=StateEffect.FLIP,
    addressed_state=AddressedState.AUTO,
    addressed_m=M_AUTO,
    delta_m=1,
):
    return IntentEvent(
        t_start_s=0.0,
        duration_s=0.0,
        kind=kind,
        state_effect=state_effect,
        addressed_state=addressed_state,
        addressed_m=addressed_m,
        delta_m=delta_m,
    )


def test_coerces_ints_to_enums():
    # Raw ints are accepted and normalised to the enums.
    e = IntentEvent(0.0, 0.0, 0, 0, -1, M_AUTO, 1)
    assert e.kind is Kind.PULSE
    assert e.state_effect is StateEffect.FLIP
    assert e.addressed_state is AddressedState.AUTO


def test_rejects_unknown_codes():
    with pytest.raises(ValueError):
        _event(kind=99)
    with pytest.raises(ValueError):
        _event(state_effect=99)
    with pytest.raises(ValueError):
        _event(addressed_state=99)


def test_t_centre_is_event_midpoint():
    e = IntentEvent(
        1.0, 0.4, Kind.PULSE, StateEffect.FLIP, AddressedState.AUTO, M_AUTO, 1
    )
    assert e.t_centre_s == pytest.approx(1.2)


def test_addresses_pair_both_auto_matches_everything():
    e = _event(addressed_state=AddressedState.AUTO, addressed_m=M_AUTO)
    assert e.addresses_pair(is_ground=True, m=0)
    assert e.addresses_pair(is_ground=False, m=7)


def test_addresses_pair_m_auto_matches_by_state():
    # State declared (ground), momentum class automatic: every ground branch.
    e = _event(addressed_state=AddressedState.GROUND, addressed_m=M_AUTO)
    assert e.addresses_pair(is_ground=True, m=3)
    assert not e.addresses_pair(is_ground=False, m=3)


def test_addresses_pair_state_auto_matches_by_m():
    # Momentum class declared, state automatic: every branch at that m.
    e = _event(addressed_state=AddressedState.AUTO, addressed_m=5)
    assert e.addresses_pair(is_ground=True, m=5)
    assert e.addresses_pair(is_ground=False, m=5)
    assert not e.addresses_pair(is_ground=True, m=4)


def test_addresses_pair_both_declared_ground():
    # Addressed pair |g, 5> <-> |e, 6| for a ground-addressed up pulse.
    e = _event(addressed_state=AddressedState.GROUND, addressed_m=5, delta_m=1)
    assert e.addresses_pair(is_ground=True, m=5)  # the ground member
    assert e.addresses_pair(is_ground=False, m=6)  # the excited member
    assert not e.addresses_pair(is_ground=True, m=6)  # wrong-side ground
    assert not e.addresses_pair(is_ground=False, m=5)  # wrong-side excited
    assert not e.addresses_pair(is_ground=True, m=3)  # parked arm untouched


def test_addresses_pair_both_declared_excited_resolves_same_pair():
    # An excited-addressed pulse on the same physical pair |g, 5> <-> |e, 6|.
    e = _event(addressed_state=AddressedState.EXCITED, addressed_m=6, delta_m=1)
    assert e.addresses_pair(is_ground=False, m=6)
    assert e.addresses_pair(is_ground=True, m=5)
    assert not e.addresses_pair(is_ground=True, m=6)


def test_internal_state_population_is_sortable():
    # A mixed-state population (e.g. the open arms of a Mach-Zehnder) must be
    # sortable: the compiler logs sorted(final_population), which crashed when
    # InternalState was not orderable.
    population = {(GROUND, 3), (EXCITED, 2), (GROUND, 0), (EXCITED, 5)}
    assert sorted(population) == sorted(population)  # deterministic, no TypeError
    # Ordered by the "g"/"e" value, then m: excited ("e") sorts before ground.
    assert sorted(population) == [
        (EXCITED, 2),
        (EXCITED, 5),
        (GROUND, 0),
        (GROUND, 3),
    ]
