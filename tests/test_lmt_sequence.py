"""
Tests for the declarative LMT sequence language and compiler.
"""

import pytest

from repository.lib.lmt_sequence import EVENT_CALLBACK
from repository.lib.lmt_sequence import EVENT_CLEAROUT
from repository.lib.lmt_sequence import EVENT_PHASE
from repository.lib.lmt_sequence import EVENT_PULSE
from repository.lib.lmt_sequence import EVENT_SETPOINT
from repository.lib.lmt_sequence import EVENT_WAIT
from repository.lib.lmt_sequence import Beam
from repository.lib.lmt_sequence import Callback
from repository.lib.lmt_sequence import CallbackAction
from repository.lib.lmt_sequence import Clearout
from repository.lib.lmt_sequence import Phase
from repository.lib.lmt_sequence import SequenceError
from repository.lib.lmt_sequence import SetPoint
from repository.lib.lmt_sequence import Wait
from repository.lib.lmt_sequence import compile_sequence
from repository.lib.lmt_sequence import ladder
from repository.lib.lmt_sequence import pi
from repository.lib.lmt_sequence import pi2
from repository.lib.physics import lmt_resonance as pulse_intent
from repository.lib.physics.lmt_resonance import EXCITED
from repository.lib.physics.lmt_resonance import GROUND
from repository.lib.physics.lmt_resonance import StateEffect
from repository.lib.physics.lmt_resonance import opll_m_term_hz


def setpoints(rabi_up=9e3, rabi_down=7e3):
    """A full-intensity SetPoint declaring both beams' Rabi frequencies."""
    return [SetPoint(setpoint=2.6, rabi_up=rabi_up, rabi_down=rabi_down)]


def test_beam_sign():
    assert Beam.UP.sign == 1
    assert Beam.DOWN.sign == -1


def test_setpoint_validation():
    with pytest.raises(ValueError, match="at least one beam"):
        SetPoint(setpoint=2.6)
    with pytest.raises(ValueError, match="rabi_down"):
        SetPoint(setpoint=2.6, rabi_down=-1.0)
    with pytest.raises(ValueError, match="non-negative"):
        SetPoint(setpoint=-0.1, rabi_up=1e3)


def test_ladder_helper():
    rungs = ladder(start_m=3, n=4, first_beam=Beam.DOWN)
    assert [p.m for p in rungs] == [3, 4, 5, 6]
    assert [p.beam for p in rungs] == [Beam.DOWN, Beam.UP, Beam.DOWN, Beam.UP]
    assert all(p.area == 1.0 for p in rungs)


def test_ladder_helper_descending():
    # Descending re-uses the same first_beam value as the matching ascending
    # ladder; the beam sequence is inverted internally (UP/DOWN swapped
    # relative to the ascending case) to keep addressing populated states -
    # see _raise_arm/_lower_arm for the underlying beam-per-direction rule.
    rungs = ladder(start_m=6, n=4, first_beam=Beam.DOWN, direction=-1)
    assert [p.m for p in rungs] == [6, 5, 4, 3]
    assert [p.beam for p in rungs] == [Beam.UP, Beam.DOWN, Beam.UP, Beam.DOWN]


def test_ladder_helper_rejects_invalid_direction():
    with pytest.raises(ValueError):
        ladder(start_m=3, n=4, first_beam=Beam.DOWN, direction=2)


def test_symmetric_mach_zehnder_compiles_and_closes():
    """The canonical launch + Mach-Zehnder sequence compiles, and the
    interferometer output pair is the final population."""
    sequence = [
        *setpoints(),
        *ladder(start_m=1, n=12, first_beam=Beam.DOWN),
        Clearout(),
        pi2(Beam.DOWN, m=13),
        Wait(t=1e-3, label="dark"),
        pi(Beam.DOWN, m=13),
        Wait(t=1e-3, label="dark"),
        pi2(Beam.DOWN, m=13),
    ]
    compiled = compile_sequence(sequence, initial_population={(EXCITED, 1)})
    assert len(compiled) == len(sequence)
    # 12 launch pulses end excited at m = 13 (down-first ladder flips state
    # every pulse, starting from excited)
    # The interferometer operates on the pair |e, 13> <-> |g, 14>
    assert compiled.final_population == frozenset({(EXCITED, 13), (GROUND, 14)})

    kinds = [e.kind for e in compiled.events]
    assert kinds[0] == EVENT_SETPOINT
    assert kinds[1:13] == [EVENT_PULSE] * 12
    assert kinds[13] == EVENT_CLEAROUT
    assert kinds[14:] == [
        EVENT_PULSE,
        EVENT_WAIT,
        EVENT_PULSE,
        EVENT_WAIT,
        EVENT_PULSE,
    ]


def test_compiles_phase_event():
    """A Phase event compiles to an EVENT_PHASE with a phase parameter and has no
    effect on the population walk."""
    without_phase = [
        *setpoints(),
        pi2(Beam.DOWN, m=1),
        pi(Beam.DOWN, m=1),
    ]
    with_phase = [
        setpoints()[0],
        Phase(phase=0.25, label="bs"),
        pi2(Beam.DOWN, m=1),
        Phase(phase=0.5),
        pi(Beam.DOWN, m=1),
    ]

    base = compile_sequence(without_phase, initial_population={(GROUND, 1)})
    compiled = compile_sequence(with_phase, initial_population={(GROUND, 1)})

    # Same final population: the Phase events are inert to the atoms.
    assert compiled.final_population == base.final_population

    phase_events = [e for e in compiled.events if e.kind == EVENT_PHASE]
    assert len(phase_events) == 2
    first = phase_events[0]
    assert first.phase_param is not None
    assert first.phase_param.default == 0.25
    assert "bs" in first.phase_param.attr_name
    assert first.phase_param.attr_name.endswith("phase_bs")


def test_phase_event_allowed_before_setpoint():
    """A Phase before any SetPoint is legal (it fires no pulse)."""
    compiled = compile_sequence(
        [Phase(phase=0.1), *setpoints(), pi(Beam.UP, m=0)],
        initial_population={(GROUND, 0)},
    )
    assert compiled.events[0].kind == EVENT_PHASE


def test_phase_validation():
    with pytest.raises(ValueError):
        Phase()
    with pytest.raises(ValueError):
        Phase(phase=0.25, param="some_param")
    with pytest.raises(ValueError):
        Phase(phase=0.25, multiplier=2.0)
    compiled = compile_sequence(
        [*setpoints(), Phase(param="interferometer_phase")],
        initial_population={(GROUND, 0)},
    )
    assert compiled.events[-1].phase_param_ref == "interferometer_phase"
    assert compiled.events[-1].phase_param is None
    assert compiled.events[-1].phase_multiplier == 1.0


def test_phase_multiplier():
    compiled = compile_sequence(
        [*setpoints(), Phase(param="interferometer_phase", multiplier=-2.0)],
        initial_population={(GROUND, 0)},
    )
    assert compiled.events[-1].phase_param_ref == "interferometer_phase"
    assert compiled.events[-1].phase_multiplier == -2.0


def test_velocity_selective_slice_sequence():
    """The canonical full sequence starting from release: the
    velocity-selective pulse is just a normal pulse with a longer duration
    (from its low-set-point Rabi frequency), followed by launch and MZ."""
    slice_rabi = 1 / (2 * 380e-6)
    sequence = [
        SetPoint(setpoint=0.012, rabi_up=slice_rabi, label="slice"),  # 0
        pi(Beam.UP, m=0, label="slice"),  # 1
        SetPoint(setpoint=2.6, rabi_up=9e3, rabi_down=7e3),  # 2
        Clearout(),  # 3
        *ladder(start_m=1, n=12, first_beam=Beam.DOWN),  # 4..15
        Clearout(),  # 16
        pi2(Beam.DOWN, m=13),
        Wait(t=1e-3),
        pi(Beam.DOWN, m=13),
        Wait(t=1e-3),
        pi2(Beam.DOWN, m=13),
    ]
    compiled = compile_sequence(sequence, initial_population={(GROUND, 0)})
    assert compiled.final_population == frozenset({(EXCITED, 13), (GROUND, 14)})

    slice_pulse = compiled.events[1]
    assert slice_pulse.kind == EVENT_PULSE
    # Duration default follows the slice SetPoint's declared Rabi frequency
    assert slice_pulse.duration_param.default == pytest.approx(380e-6)
    assert slice_pulse.governing_setpoint_index == 0
    # Labels make the generated parameters recognisable in the ndscan UI
    slice_setpoint = compiled.events[0]
    assert slice_setpoint.setpoint_param.attr_name == "p00_setpoint_slice"
    assert "'slice'" in slice_setpoint.setpoint_param.description
    assert "'slice'" in slice_pulse.offset_param.description
    # Later pulses are governed by the full-intensity set point instead
    first_launch_pulse = compiled.events[4]
    assert first_launch_pulse.kind == EVENT_PULSE
    assert first_launch_pulse.governing_setpoint_index == 2


def test_pi_swaps_and_pi2_branches():
    # pi/2 populates both sides of the pair
    compiled = compile_sequence(
        [*setpoints(), pi2(Beam.UP, m=0)], initial_population={(GROUND, 0)}
    )
    assert compiled.final_population == frozenset({(GROUND, 0), (EXCITED, 1)})

    # pi swaps: single-side input moves entirely to the other side
    compiled = compile_sequence(
        [*setpoints(), pi(Beam.UP, m=0)], initial_population={(GROUND, 0)}
    )
    assert compiled.final_population == frozenset({(EXCITED, 1)})

    # pi on a fully-populated pair keeps both sides (they swap)
    compiled = compile_sequence(
        [*setpoints(), pi2(Beam.UP, m=0), pi(Beam.UP, m=0)],
        initial_population={(GROUND, 0)},
    )
    assert compiled.final_population == frozenset({(GROUND, 0), (EXCITED, 1)})


def test_unpopulated_pulse_raises_with_index():
    sequence = [*setpoints(), pi(Beam.UP, m=5)]
    with pytest.raises(SequenceError, match="Event 1.*m=5"):
        compile_sequence(sequence, initial_population={(GROUND, 0)})


def test_unpopulated_pulse_with_state_warns_when_not_strict(caplog):
    sequence = [*setpoints(), pi(Beam.UP, m=5, state=GROUND)]
    # strict: error
    with pytest.raises(SequenceError):
        compile_sequence(sequence, initial_population={(GROUND, 0)})
    # non-strict with explicit state: warning only
    with caplog.at_level("WARNING"):
        compiled = compile_sequence(
            sequence, initial_population={(GROUND, 0)}, strict=False
        )
    assert any("not populated" in r.message for r in caplog.records)
    assert (EXCITED, 6) in compiled.final_population


def test_unpopulated_pulse_without_state_always_raises():
    sequence = [*setpoints(), pi(Beam.UP, m=5)]
    with pytest.raises(SequenceError, match="state="):
        compile_sequence(sequence, initial_population={(GROUND, 0)}, strict=False)


def test_ambiguous_pulse_requires_state():
    # Populate both internal states at the same m: the pulse cannot know
    # which transition is meant without an explicit state.
    sequence = [*setpoints(), pi(Beam.UP, m=1)]
    with pytest.raises(SequenceError, match="disambiguate"):
        compile_sequence(sequence, initial_population={(GROUND, 1), (EXCITED, 1)})
    # With an explicit state it compiles: (g, 1) swaps to (e, 2) while the
    # unaddressed (e, 1) population is untouched
    compiled = compile_sequence(
        [*setpoints(), pi(Beam.UP, m=1, state=GROUND)],
        initial_population={(GROUND, 1), (EXCITED, 1)},
    )
    assert compiled.final_population == frozenset({(EXCITED, 1), (EXCITED, 2)})


def test_pulse_before_setpoint_raises():
    with pytest.raises(SequenceError, match="SetPoint"):
        compile_sequence([pi(Beam.UP, m=0)], initial_population={(GROUND, 0)})
    # A set point that does not declare this beam's Rabi frequency is an
    # error too: the pulse's default duration would be undefined
    with pytest.raises(SequenceError, match="rabi_up"):
        compile_sequence(
            [SetPoint(setpoint=2.6, rabi_down=7e3), pi(Beam.UP, m=0)],
            initial_population={(GROUND, 0)},
        )


def test_durations_follow_governing_setpoint():
    sequence = [
        SetPoint(setpoint=2.6, rabi_up=10e3),
        pi(Beam.UP, m=0),
        pi2(Beam.UP, m=1, state=EXCITED),
        SetPoint(setpoint=0.5, rabi_up=2e3),
        pi(Beam.UP, m=1, state=EXCITED),
    ]
    compiled = compile_sequence(sequence, initial_population={(GROUND, 0)})
    pulses = [e for e in compiled.events if e.kind == EVENT_PULSE]
    # pi at 10 kHz Rabi: 1 / (2 * 10 kHz) = 50 us
    assert pulses[0].duration_param.default == pytest.approx(50e-6)
    # pi/2 at 10 kHz Rabi: 25 us
    assert pulses[1].duration_param.default == pytest.approx(25e-6)
    # pi at 2 kHz Rabi after the set-point change: 250 us
    assert pulses[2].duration_param.default == pytest.approx(250e-6)
    # Governing set-point indices point at the right SetPoint events
    assert pulses[0].governing_setpoint_index == 0
    assert pulses[1].governing_setpoint_index == 0
    assert pulses[2].governing_setpoint_index == 3


def test_offset_param_defaults_to_zero():
    compiled = compile_sequence(
        [*setpoints(), pi(Beam.UP, m=0)], initial_population={(GROUND, 0)}
    )
    pulse = compiled.events[-1]
    assert pulse.offset_param.default == 0.0
    assert pulse.offset_param.unit == "kHz"


def test_clearout_population_rules():
    # Clearout drops ground states only
    compiled = compile_sequence(
        [*setpoints(), pi2(Beam.UP, m=0), Clearout()],
        initial_population={(GROUND, 0)},
    )
    assert compiled.final_population == frozenset({(EXCITED, 1)})

    # Clearout that would empty the population raises in strict mode
    with pytest.raises(SequenceError, match="all remaining population"):
        compile_sequence([*setpoints(), Clearout()], initial_population={(GROUND, 0)})

    # ... and only warns when strict=False
    compiled = compile_sequence(
        [*setpoints(), Clearout()], initial_population={(GROUND, 0)}, strict=False
    )
    assert compiled.final_population == frozenset()

    # Clearout with explicit duration spawns its own parameter
    compiled = compile_sequence(
        [*setpoints(), Clearout(duration=80e-6)], initial_population={(EXCITED, 0)}
    )
    clearout = compiled.events[-1]
    assert clearout.duration_param.default == pytest.approx(80e-6)
    assert clearout.duration_param_ref is None
    # Default clearout reuses the shared parameter
    compiled = compile_sequence(
        [*setpoints(), Clearout()], initial_population={(EXCITED, 0)}
    )
    assert compiled.events[-1].duration_param_ref == "clearout_duration"


def test_compiled_pulse_intent_fields():
    """Pulses carry their resolved intent: a pi pulse is a FLIP, anything
    else a SUPERPOSE, with the addressed state/m as resolved by the
    population walk and delta_m equal to the beam sign."""
    compiled = compile_sequence(
        [*setpoints(), pi(Beam.UP, m=0), pi2(Beam.DOWN, m=1)],
        initial_population={(GROUND, 0)},
    )
    pi_event = compiled.events[1]
    assert pi_event.state_effect == pulse_intent.StateEffect.FLIP
    assert pi_event.addressed_state == pulse_intent.AddressedState.GROUND
    assert pi_event.addressed_m == 0
    assert pi_event.delta_m == 1

    # After the pi the population is {(e, 1)}; the down-beam pi/2 addresses it
    pi2_event = compiled.events[2]
    assert pi2_event.state_effect == pulse_intent.StateEffect.SUPERPOSE
    assert pi2_event.addressed_state == pulse_intent.AddressedState.EXCITED
    assert pi2_event.addressed_m == 1
    assert pi2_event.delta_m == -1

    # Non-pulse events keep the inert defaults
    setpoint_event = compiled.events[0]
    assert setpoint_event.state_effect == pulse_intent.StateEffect.NONE
    assert setpoint_event.addressed_state == pulse_intent.AddressedState.AUTO
    assert setpoint_event.addressed_m == pulse_intent.M_AUTO
    assert setpoint_event.delta_m == 0
    assert setpoint_event.declared_duration_s == 0.0


def test_compiled_callback_intent_fields():
    """A callback compiles to a EVENT_CALLBACK event carrying its declared
    actions as integer 4-tuples ``(addressed_state, addressed_m, delta_m,
    state_effect)`` - one per :class:`CallbackAction` - ready to be flattened
    into ordinary pulse intent rows at fire time."""
    compiled = compile_sequence(
        [
            *setpoints(),
            Callback(
                callback_id=7,
                actions=[
                    CallbackAction(
                        state=EXCITED, m=0, delta_m=-2, state_effect=StateEffect.FLIP
                    )
                ],
                duration=1.5e-3,
            ),
            Callback(
                callback_id=8,
                actions=[
                    CallbackAction(
                        state=GROUND, m=2, delta_m=1, state_effect=StateEffect.SUPERPOSE
                    )
                ],
            ),
            Callback(callback_id=9),  # empty: pure external trigger
        ],
        initial_population={(EXCITED, 0)},
    )
    flip = compiled.events[1]
    assert flip.kind == EVENT_CALLBACK
    assert flip.callback_id == 7
    assert flip.declared_duration_s == pytest.approx(1.5e-3)
    # One action, encoded as (addressed_state, addressed_m, delta_m, state_effect)
    assert flip.callback_actions == (
        (
            int(pulse_intent.AddressedState.EXCITED),
            0,
            -2,
            int(StateEffect.FLIP),
        ),
    )

    superpose = compiled.events[2]
    assert superpose.callback_actions == (
        (
            int(pulse_intent.AddressedState.GROUND),
            2,
            1,
            int(StateEffect.SUPERPOSE),
        ),
    )

    # An empty callback carries no actions and its inert per-event defaults.
    empty = compiled.events[3]
    assert empty.kind == EVENT_CALLBACK
    assert empty.callback_actions == ()
    assert empty.state_effect == pulse_intent.StateEffect.NONE
    assert empty.declared_duration_s == 0.0


def test_callback_bookkeeping():
    """A Callback's declared actions keep the population walk - and therefore
    later pulses - correct. A FLIP action on (e, 0) with delta_m=-2 transfers it
    to (g, 2), so the following up-pi on (g, 2) closes at (e, 3)."""
    sequence = [
        *setpoints(),
        Callback(
            callback_id=1,
            actions=[
                CallbackAction(
                    state=EXCITED, m=0, delta_m=-2, state_effect=StateEffect.FLIP
                )
            ],
        ),
        pi(Beam.UP, m=2),  # input must now be (g, 2)
    ]
    compiled = compile_sequence(sequence, initial_population={(EXCITED, 0)})
    assert compiled.events[1].kind == EVENT_CALLBACK
    assert compiled.events[1].callback_id == 1
    assert compiled.final_population == frozenset({(EXCITED, 3)})


def test_empty_callback_is_inert():
    """An empty callback (only an external trigger) leaves the population walk
    unchanged and emits a single EVENT_CALLBACK carrying no actions."""
    sequence = [
        *setpoints(),
        Callback(callback_id=5, actions=[]),
        pi(Beam.UP, m=0),
    ]
    compiled = compile_sequence(sequence, initial_population={(GROUND, 0)})
    assert compiled.events[1].kind == EVENT_CALLBACK
    assert compiled.events[1].callback_actions == ()
    # The pi still sees the untouched (g, 0) population and flips it to (e, 1).
    assert compiled.final_population == frozenset({(EXCITED, 1)})


def _shaped_double_actions():
    """The two-cloud shaped-pulse callback actions (up-beam pi on each cloud)."""
    return [
        CallbackAction(state=EXCITED, m=1, delta_m=1, state_effect=StateEffect.FLIP),
        CallbackAction(state=GROUND, m=2, delta_m=1, state_effect=StateEffect.FLIP),
    ]


def test_callback_bakes_setpoint_rabi_and_m_terms():
    """A shaped-pulse callback captures the governing set point's Rabi (for the
    beam its actions drive) and each action's recoil m-term, so the engine can
    reconstruct each cloud's resonance - and its probe Stark shift - itself."""
    compiled = compile_sequence(
        [
            *setpoints(rabi_up=9.1e3),
            Callback(callback_id=1, actions=_shaped_double_actions()),
        ],
        initial_population={(EXCITED, 1), (GROUND, 2)},
    )
    cb = compiled.events[1]
    assert cb.kind == EVENT_CALLBACK
    # Up-beam actions -> up-beam Rabi and beam sign, from the governing set point.
    assert cb.beam_sign == 1
    assert cb.rabi_hz == pytest.approx(9.1e3)
    assert cb.governing_setpoint_index == 0
    # One m-term per action, identical to what opll_m_term_hz gives for each.
    assert cb.callback_action_m_term_hz == pytest.approx(
        (
            opll_m_term_hz(1, EXCITED, 1),
            opll_m_term_hz(2, GROUND, 1),
        )
    )


def test_callback_drive_matches_equivalent_pulse():
    """The Rabi and m-term a callback action bakes equal those an ordinary pulse
    at the same set point addressing the same cloud would carry."""
    cb = compile_sequence(
        [
            *setpoints(rabi_up=8.3e3),
            Callback(
                callback_id=1,
                actions=[
                    CallbackAction(
                        state=GROUND, m=2, delta_m=1, state_effect=StateEffect.FLIP
                    )
                ],
            ),
        ],
        initial_population={(GROUND, 2)},
    ).events[1]
    pulse = compile_sequence(
        [*setpoints(rabi_up=8.3e3), pi(Beam.UP, m=2)],
        initial_population={(GROUND, 2)},
    ).events[1]
    assert cb.rabi_hz == pytest.approx(pulse.rabi_hz)
    assert cb.callback_action_m_term_hz[0] == pytest.approx(pulse.m_term_hz)


def test_callback_down_beam_uses_rabi_down():
    cb = compile_sequence(
        [
            *setpoints(rabi_down=7.4e3),
            Callback(
                callback_id=1,
                actions=[
                    CallbackAction(
                        state=EXCITED, m=1, delta_m=-1, state_effect=StateEffect.FLIP
                    )
                ],
            ),
        ],
        initial_population={(EXCITED, 1)},
    ).events[1]
    assert cb.beam_sign == -1
    assert cb.rabi_hz == pytest.approx(7.4e3)


def test_empty_callback_has_no_drive():
    """An empty callback drives no beam: no Rabi, no m-terms, no governing
    set point (and it needs none, so it is legal before any SetPoint)."""
    cb = compile_sequence(
        [Callback(callback_id=9, actions=[])],
        initial_population={(EXCITED, 5)},
    ).events[0]
    assert cb.beam_sign == 0
    assert cb.rabi_hz == 0.0
    assert cb.governing_setpoint_index == -1
    assert cb.callback_action_m_term_hz == ()


def test_callback_mixed_beams_rejected():
    with pytest.raises(SequenceError, match="drive both beams"):
        compile_sequence(
            [
                *setpoints(),
                Callback(
                    callback_id=1,
                    actions=[
                        CallbackAction(
                            state=EXCITED, m=1, delta_m=1, state_effect=StateEffect.FLIP
                        ),
                        CallbackAction(
                            state=GROUND, m=2, delta_m=-1, state_effect=StateEffect.FLIP
                        ),
                    ],
                ),
            ],
            initial_population={(EXCITED, 1), (GROUND, 2)},
        )


def test_callback_with_actions_before_setpoint_rejected():
    with pytest.raises(SequenceError, match="before any.*SetPoint"):
        compile_sequence(
            [Callback(callback_id=1, actions=_shaped_double_actions())],
            initial_population={(EXCITED, 1), (GROUND, 2)},
        )


def test_callback_missing_beam_rabi_rejected():
    """An up-beam callback at a set point that declares only rabi_down fails the
    same way an up-beam pulse there would."""
    with pytest.raises(SequenceError, match="rabi_up"):
        compile_sequence(
            [
                SetPoint(setpoint=2.6, rabi_down=7e3),
                Callback(
                    callback_id=1,
                    actions=[
                        CallbackAction(
                            state=EXCITED, m=1, delta_m=1, state_effect=StateEffect.FLIP
                        )
                    ],
                ),
            ],
            initial_population={(EXCITED, 1)},
        )


def test_param_naming():
    sequence = [
        SetPoint(setpoint=2.6, rabi_up=10e3, rabi_down=7e3),
        pi2(Beam.DOWN, m=12),
        Wait(t=1e-3, label="dark"),
        pi(Beam.UP, m=13, label="mirror"),
    ]
    compiled = compile_sequence(sequence, initial_population={(EXCITED, 12)})
    events = compiled.events
    assert events[0].setpoint_param.attr_name == "p00_setpoint"
    assert events[1].offset_param.attr_name == "p01_pi2_d_m12_offset"
    assert events[1].duration_param.attr_name == "p01_pi2_d_m12_duration"
    assert events[2].duration_param.attr_name == "p02_wait_dark_duration"
    assert events[3].offset_param.attr_name == "p03_pi_u_m13_mirror_offset"
    assert "setpoint" in events[0].setpoint_param.description
    # All generated names are valid identifiers and group by event when
    # sorted alphabetically (the p{index:02d} prefix dominates the sort)
    names = [
        spec.attr_name
        for e in events
        for spec in (e.offset_param, e.duration_param, e.setpoint_param)
        if spec is not None
    ]
    assert all(name.isidentifier() for name in names)
    prefixes = [name[:3] for name in names]
    assert prefixes == sorted(prefixes)


def test_negative_m_naming():
    compiled = compile_sequence(
        [*setpoints(), pi(Beam.DOWN, m=-3, state=GROUND)],
        initial_population={(GROUND, -3)},
    )
    assert compiled.events[-1].offset_param.attr_name == "p01_pi_d_mn3_offset"


def test_wait_validation():
    with pytest.raises(ValueError):
        Wait()
    with pytest.raises(ValueError):
        Wait(t=1e-3, param="some_param")
    compiled = compile_sequence(
        [*setpoints(), Wait(param="delay_between_pulses")],
        initial_population={(GROUND, 0)},
    )
    assert compiled.events[-1].duration_param_ref == "delay_between_pulses"


def test_empty_sequence_raises():
    with pytest.raises(SequenceError):
        compile_sequence([], initial_population={(GROUND, 0)})


def test_bad_initial_population_raises():
    with pytest.raises(SequenceError):
        compile_sequence([*setpoints()], initial_population={("x", 0)})


def test_unknown_event_raises():
    with pytest.raises(SequenceError, match="unknown"):
        compile_sequence([*setpoints(), "pi u 0"], initial_population={(GROUND, 0)})
