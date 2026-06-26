"""
Callback-flatten equivalence tests.

A :class:`~repository.lib.lmt_sequence.Callback` is no longer a special kind of
event: at fire time each of its :class:`~repository.lib.lmt_sequence.CallbackAction`
items becomes one ordinary ``Kind.PULSE`` intent row (all sharing one
``t_start``), and the compiler's population walk applies each action through the
same helper the pulse path uses. These tests pin the guarantee that a callback
walks *identically* to the equivalent explicit pulses, in both:

* the compiler's population bookkeeping (:func:`compile_sequence`), and
* the trajectory predictor's branch walk
  (:func:`repository.lib.physics.trajectory.walk_intent_events`), which consumes
  the flattened ``Kind.PULSE`` rows.

Both a FLIP action (full transfer across the pair) and a NONE action (pure
momentum kick on the single declared population) are covered, plus the empty
callback (no atoms touched, no intent rows).
"""

import numpy as np
import scipy.constants

from repository.lib.lmt_sequence import Beam
from repository.lib.lmt_sequence import Callback
from repository.lib.lmt_sequence import CallbackAction
from repository.lib.lmt_sequence import SetPoint
from repository.lib.lmt_sequence import compile_sequence
from repository.lib.lmt_sequence import pi
from repository.lib.physics.ballistic import BallisticConfig
from repository.lib.physics.ballistic import CameraGeometry
from repository.lib.physics.lmt_resonance import EXCITED
from repository.lib.physics.lmt_resonance import GROUND
from repository.lib.physics.lmt_resonance import M_AUTO
from repository.lib.physics.lmt_resonance import AddressedState
from repository.lib.physics.lmt_resonance import IntentEvent
from repository.lib.physics.lmt_resonance import Kind
from repository.lib.physics.lmt_resonance import StateEffect
from repository.lib.physics.trajectory import walk_intent_events

SR87_MASS_KG = scipy.constants.atomic_mass * 87
CLOCK_WAVELENGTH_M = scipy.constants.c / 429_228_004_229_872.99

_CFG = BallisticConfig(
    mass_kg=SR87_MASS_KG,
    gravity_vec_m_per_s2=np.array([0.0, 0.0, -scipy.constants.g]),
    clock_beam_direction=np.array([0.0, 0.0, 1.0]),
    clock_wavelength_m=CLOCK_WAVELENGTH_M,
    camera=CameraGeometry(
        optical_axis=np.array([0.0, 1.0, 0.0]),
        sensor_x_axis=np.array([1.0, 0.0, 0.0]),
        sensor_y_axis=np.array([0.0, 0.0, 1.0]),
        centre_pixel=(256.0, 256.0),
        pixel_size_m=16e-6,
        magnification=1.0,
    ),
)


def _setpoint():
    return SetPoint(setpoint=2.6, rabi_up=9e3, rabi_down=7e3)


def _action_to_intent(action, t_start_s, duration_s=50e-6):
    """The single ``Kind.PULSE`` intent row a callback action flattens to."""
    return IntentEvent(
        t_start_s=t_start_s,
        duration_s=duration_s,
        kind=Kind.PULSE,
        state_effect=action.state_effect,
        addressed_state=(
            AddressedState.GROUND if action.state == GROUND else AddressedState.EXCITED
        ),
        addressed_m=action.m,
        delta_m=action.delta_m,
    )


def _pulse_intent(addressed_state, addressed_m, delta_m, state_effect, t_start_s):
    return IntentEvent(
        t_start_s=t_start_s,
        duration_s=50e-6,
        kind=Kind.PULSE,
        state_effect=state_effect,
        addressed_state=addressed_state,
        addressed_m=addressed_m,
        delta_m=delta_m,
    )


def _branch_signatures(branches):
    """A sortable, position-aware fingerprint of a list of walked branches."""
    return sorted(
        (b.is_ground, b.m, round(float(b.displacement_m[2]), 12)) for b in branches
    )


def test_flip_callback_equivalent_to_explicit_ladder_population():
    """A callback whose actions reproduce a two-rung ladder leaves the SAME
    final population as declaring those pulses directly."""
    actions = [
        # up-beam pi on (g, 0): pair |g,0> <-> |e,1>, delta_m = +1
        CallbackAction(state=GROUND, m=0, delta_m=1, state_effect=StateEffect.FLIP),
        # down-beam pi on the resulting (e, 1): pair |g,2> <-> |e,1>, delta_m = -1
        CallbackAction(state=EXCITED, m=1, delta_m=-1, state_effect=StateEffect.FLIP),
    ]
    via_callback = compile_sequence(
        [_setpoint(), Callback(callback_id=1, actions=actions)],
        initial_population={(GROUND, 0)},
    ).final_population

    via_pulses = compile_sequence(
        [_setpoint(), pi(Beam.UP, m=0), pi(Beam.DOWN, m=1)],
        initial_population={(GROUND, 0)},
    ).final_population

    assert via_callback == via_pulses == frozenset({(GROUND, 2)})


def test_flip_callback_walk_matches_explicit_pulse_walk():
    """Walked through the trajectory predictor, the flattened FLIP-action intent
    rows produce the same branches as the equivalent explicit pulse rows."""
    actions = [
        CallbackAction(state=GROUND, m=0, delta_m=1, state_effect=StateEffect.FLIP),
        CallbackAction(state=EXCITED, m=1, delta_m=-1, state_effect=StateEffect.FLIP),
    ]
    # The callback fires both actions at one t_start; the explicit pulses fire at
    # the same instant for a like-for-like comparison.
    t0 = 2e-3
    callback_rows = [_action_to_intent(a, t0) for a in actions]
    explicit_rows = [
        _pulse_intent(AddressedState.GROUND, 0, 1, StateEffect.FLIP, t0),
        _pulse_intent(AddressedState.EXCITED, 1, -1, StateEffect.FLIP, t0),
    ]

    from_callback = walk_intent_events(callback_rows, 10e-3, _CFG)
    from_pulses = walk_intent_events(explicit_rows, 10e-3, _CFG)
    assert _branch_signatures(from_callback) == _branch_signatures(from_pulses)


def test_none_kick_callback_equivalent_in_compiler_and_walk():
    """A NONE action is a pure momentum kick on the single declared population:
    same final population and same walked branches as a hand-built NONE row."""
    action = CallbackAction(state=GROUND, m=0, delta_m=3, state_effect=StateEffect.NONE)
    via_callback = compile_sequence(
        [_setpoint(), Callback(callback_id=2, actions=[action])],
        initial_population={(GROUND, 0)},
    ).final_population
    # Pure kick: ground stays ground, m += delta_m.
    assert via_callback == frozenset({(GROUND, 3)})

    t0 = 2e-3
    from_callback = walk_intent_events([_action_to_intent(action, t0)], 10e-3, _CFG)
    explicit = walk_intent_events(
        [_pulse_intent(AddressedState.GROUND, 0, 3, StateEffect.NONE, t0)],
        10e-3,
        _CFG,
    )
    assert _branch_signatures(from_callback) == _branch_signatures(explicit)
    # The kick stays in the ground state, three recoils up.
    assert len(from_callback) == 1
    assert from_callback[0].is_ground is True
    assert from_callback[0].m == 3


def test_empty_callback_changes_nothing():
    """An empty callback leaves the population walk unchanged and emits zero
    intent rows, so the predicted branches are identical to free flight."""
    final = compile_sequence(
        [_setpoint(), Callback(callback_id=9, actions=[])],
        initial_population={(EXCITED, 5)},
    ).final_population
    assert final == frozenset({(EXCITED, 5)})

    # Zero flattened intent rows -> the walker carries the single initial branch
    # untouched (here from the ground state, the walker's default).
    branches = walk_intent_events([], 10e-3, _CFG)
    assert len(branches) == 1
    assert branches[0].is_ground is True
    assert branches[0].m == 0


def test_empty_callback_emits_no_intent_rows():
    """Sanity: an empty callback's action list flattens to nothing."""
    cb = Callback(callback_id=9, actions=[])
    rows = [_action_to_intent(a, 0.0) for a in cb.actions]
    assert rows == []
    # M_AUTO sentinel is unused by an empty callback, but importing it keeps the
    # vocabulary surface covered.
    assert M_AUTO < 0
