"""
Tests for the declarative LMT sequence language and compiler.
"""

import pytest

from repository.lib.lmt_sequence import Beam
from repository.lib.lmt_sequence import Callback
from repository.lib.lmt_sequence import Clearout
from repository.lib.lmt_sequence import EVENT_CALLBACK
from repository.lib.lmt_sequence import EVENT_CLEAROUT
from repository.lib.lmt_sequence import EVENT_PULSE
from repository.lib.lmt_sequence import EVENT_SETPOINT
from repository.lib.lmt_sequence import EVENT_WAIT
from repository.lib.lmt_sequence import Pulse
from repository.lib.lmt_sequence import SequenceError
from repository.lib.lmt_sequence import SetPoint
from repository.lib.lmt_sequence import Wait
from repository.lib.lmt_sequence import compile_sequence
from repository.lib.lmt_sequence import ladder
from repository.lib.lmt_sequence import pi
from repository.lib.lmt_sequence import pi2


def setpoints(rabi_up=9e3, rabi_down=7e3):
    return [
        SetPoint(Beam.UP, setpoint=2.6, rabi_frequency=rabi_up),
        SetPoint(Beam.DOWN, setpoint=2.6, rabi_frequency=rabi_down),
    ]


def test_beam_coercion():
    assert Pulse(1.0, "u", 0).beam is Beam.UP
    assert Pulse(1.0, "down", 0).beam is Beam.DOWN
    assert Beam.UP.sign == 1
    assert Beam.DOWN.sign == -1
    with pytest.raises(ValueError):
        Pulse(1.0, "sideways", 0)


def test_ladder_helper():
    rungs = ladder(start_m=3, n=4, first_beam="d")
    assert [p.m for p in rungs] == [3, 4, 5, 6]
    assert [p.beam for p in rungs] == [Beam.DOWN, Beam.UP, Beam.DOWN, Beam.UP]
    assert all(p.area == 1.0 for p in rungs)


def test_mach_zehnder_compiles_and_closes():
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
    compiled = compile_sequence(sequence, initial_population={("e", 1)})
    assert len(compiled) == len(sequence)
    # 12 launch pulses end excited at m = 13 (down-first ladder flips state
    # every pulse, starting from excited)
    # The interferometer operates on the pair |e, 13> <-> |g, 14>
    assert compiled.final_population == frozenset({("e", 13), ("g", 14)})

    kinds = [e.kind for e in compiled.events]
    assert kinds[:2] == [EVENT_SETPOINT, EVENT_SETPOINT]
    assert kinds[2:14] == [EVENT_PULSE] * 12
    assert kinds[14] == EVENT_CLEAROUT
    assert kinds[15:] == [
        EVENT_PULSE,
        EVENT_WAIT,
        EVENT_PULSE,
        EVENT_WAIT,
        EVENT_PULSE,
    ]


def test_pi_swaps_and_pi2_branches():
    # pi/2 populates both sides of the pair
    compiled = compile_sequence(
        [*setpoints(), pi2(Beam.UP, m=0)], initial_population={("g", 0)}
    )
    assert compiled.final_population == frozenset({("g", 0), ("e", 1)})

    # pi swaps: single-side input moves entirely to the other side
    compiled = compile_sequence(
        [*setpoints(), pi(Beam.UP, m=0)], initial_population={("g", 0)}
    )
    assert compiled.final_population == frozenset({("e", 1)})

    # pi on a fully-populated pair keeps both sides (they swap)
    compiled = compile_sequence(
        [*setpoints(), pi2(Beam.UP, m=0), pi(Beam.UP, m=0)],
        initial_population={("g", 0)},
    )
    assert compiled.final_population == frozenset({("g", 0), ("e", 1)})


def test_unpopulated_pulse_raises_with_index():
    sequence = [*setpoints(), pi(Beam.UP, m=5)]
    with pytest.raises(SequenceError, match="Event 2.*m=5"):
        compile_sequence(sequence, initial_population={("g", 0)})


def test_unpopulated_pulse_with_state_warns_when_not_strict(caplog):
    sequence = [*setpoints(), pi(Beam.UP, m=5, state="g")]
    # strict: error
    with pytest.raises(SequenceError):
        compile_sequence(sequence, initial_population={("g", 0)})
    # non-strict with explicit state: warning only
    with caplog.at_level("WARNING"):
        compiled = compile_sequence(
            sequence, initial_population={("g", 0)}, strict=False
        )
    assert any("not populated" in r.message for r in caplog.records)
    assert ("e", 6) in compiled.final_population


def test_unpopulated_pulse_without_state_always_raises():
    sequence = [*setpoints(), pi(Beam.UP, m=5)]
    with pytest.raises(SequenceError, match="state="):
        compile_sequence(sequence, initial_population={("g", 0)}, strict=False)


def test_ambiguous_pulse_requires_state():
    # After pi2 on (g,0) with the up beam, both (g,0) and (e,1) are populated.
    # A down pulse at m=1... is unambiguous; create real ambiguity instead:
    # populate (g,1) and (e,1) directly.
    sequence = [*setpoints(), pi(Beam.UP, m=1)]
    with pytest.raises(SequenceError, match="disambiguate"):
        compile_sequence(sequence, initial_population={("g", 1), ("e", 1)})
    # With an explicit state it compiles: (g, 1) swaps to (e, 2) while the
    # unaddressed (e, 1) population is untouched
    compiled = compile_sequence(
        [*setpoints(), pi(Beam.UP, m=1, state="g")],
        initial_population={("g", 1), ("e", 1)},
    )
    assert compiled.final_population == frozenset({("e", 1), ("e", 2)})


def test_pulse_before_setpoint_raises():
    with pytest.raises(SequenceError, match="SetPoint"):
        compile_sequence([pi(Beam.UP, m=0)], initial_population={("g", 0)})
    # A set point for one beam does not enable the other
    with pytest.raises(SequenceError, match="SetPoint"):
        compile_sequence(
            [SetPoint(Beam.DOWN, 2.6, 7e3), pi(Beam.UP, m=0)],
            initial_population={("g", 0)},
        )


def test_durations_follow_governing_setpoint():
    sequence = [
        SetPoint(Beam.UP, setpoint=2.6, rabi_frequency=10e3),
        pi(Beam.UP, m=0),
        pi2(Beam.UP, m=1, state="e"),
        SetPoint(Beam.UP, setpoint=0.5, rabi_frequency=2e3),
        pi(Beam.UP, m=1, state="e"),
    ]
    compiled = compile_sequence(sequence, initial_population={("g", 0)})
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
        [*setpoints(), pi(Beam.UP, m=0)], initial_population={("g", 0)}
    )
    pulse = compiled.events[-1]
    assert pulse.offset_param.default == 0.0
    assert pulse.offset_param.unit == "kHz"


def test_clearout_population_rules():
    # Clearout drops ground states only
    compiled = compile_sequence(
        [*setpoints(), pi2(Beam.UP, m=0), Clearout()],
        initial_population={("g", 0)},
    )
    assert compiled.final_population == frozenset({("e", 1)})

    # Clearout that would empty the population raises in strict mode
    with pytest.raises(SequenceError, match="all remaining population"):
        compile_sequence([*setpoints(), Clearout()], initial_population={("g", 0)})

    # ... and only warns when strict=False
    compiled = compile_sequence(
        [*setpoints(), Clearout()], initial_population={("g", 0)}, strict=False
    )
    assert compiled.final_population == frozenset()

    # Clearout with explicit duration spawns its own parameter
    compiled = compile_sequence(
        [*setpoints(), Clearout(duration=80e-6)], initial_population={("e", 0)}
    )
    clearout = compiled.events[-1]
    assert clearout.duration_param.default == pytest.approx(80e-6)
    assert clearout.duration_param_ref is None
    # Default clearout reuses the shared parameter
    compiled = compile_sequence(
        [*setpoints(), Clearout()], initial_population={("e", 0)}
    )
    assert compiled.events[-1].duration_param_ref == "clearout_duration"


def test_callback_bookkeeping():
    """A Callback's declared effect keeps later pulses valid."""
    sequence = [
        *setpoints(),
        Callback(callback_id=1, delta_m=2, state_effect="flip"),
        pi(Beam.UP, m=2),  # input must now be (g, 2)
    ]
    compiled = compile_sequence(sequence, initial_population={("e", 0)})
    assert compiled.events[2].kind == EVENT_CALLBACK
    assert compiled.events[2].callback_id == 1
    assert compiled.final_population == frozenset({("e", 3)})

    with pytest.raises(ValueError):
        Callback(callback_id=0, state_effect="explode")


def test_param_naming():
    sequence = [
        SetPoint(Beam.UP, setpoint=2.6, rabi_frequency=10e3),
        SetPoint(Beam.DOWN, setpoint=2.6, rabi_frequency=7e3),
        pi2(Beam.DOWN, m=12),
        Wait(t=1e-3, label="dark"),
        pi(Beam.UP, m=13, label="mirror"),
    ]
    compiled = compile_sequence(sequence, initial_population={("e", 12)})
    events = compiled.events
    assert events[0].setpoint_param.attr_name == "p00_setpoint_u"
    assert events[1].setpoint_param.attr_name == "p01_setpoint_d"
    assert events[2].offset_param.attr_name == "p02_pi2_d_m12_offset"
    assert events[2].duration_param.attr_name == "p02_pi2_d_m12_duration"
    assert events[3].duration_param.attr_name == "p03_wait_dark_duration"
    assert events[4].offset_param.attr_name == "p04_pi_u_m13_mirror_offset"
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
        [*setpoints(), pi(Beam.DOWN, m=-3, state="g")],
        initial_population={("g", -3)},
    )
    assert compiled.events[-1].offset_param.attr_name == "p02_pi_d_mn3_offset"


def test_wait_validation():
    with pytest.raises(ValueError):
        Wait()
    with pytest.raises(ValueError):
        Wait(t=1e-3, param="some_param")
    compiled = compile_sequence(
        [*setpoints(), Wait(param="delay_between_pulses")],
        initial_population={("g", 0)},
    )
    assert compiled.events[-1].duration_param_ref == "delay_between_pulses"


def test_empty_sequence_raises():
    with pytest.raises(SequenceError):
        compile_sequence([], initial_population={("g", 0)})


def test_bad_initial_population_raises():
    with pytest.raises(SequenceError):
        compile_sequence([*setpoints()], initial_population={("x", 0)})


def test_unknown_event_raises():
    with pytest.raises(SequenceError, match="unknown"):
        compile_sequence([*setpoints(), "pi u 0"], initial_population={("g", 0)})
