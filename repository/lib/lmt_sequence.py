"""
Declarative LMT pulse-sequence language
=======================================

Pure host-side (no ARTIQ) declaration language and "compiler" for LMT pulse
sequences. A sequence is a plain Python list of event dataclasses::

    from repository.lib.lmt_sequence import (
        Beam, Clearout, SetPoint, Wait, ladder, pi, pi2
    )

    lmt_sequence = [
        SetPoint(setpoint=2.6, rabi_up=9.1e3, rabi_down=7.4e3),
        *ladder(start_m=1, n=12, first_beam=Beam.DOWN),  # launch
        Clearout(),
        pi2(Beam.DOWN, m=13),                            # beam splitter
        Wait(t=1e-3, label="dark"),
        pi(Beam.DOWN, m=13),                             # mirror
        Wait(t=1e-3, label="dark"),
        pi2(Beam.DOWN, m=13),                            # recombiner
    ]

:func:`compile_sequence` walks the declared sequence tracking which
``(internal_state, momentum_class)`` states are populated and which delivery
set point governs each beam, validating the sequence and emitting one
:class:`CompiledEvent` per entry. The compiled events carry everything the
execution mixin (:class:`~repository.lib.experiment_templates.mixins.declarative_lmt.DeclarativeLMTBase`)
needs to spawn ndscan parameters and build its kernel-side data arrays.

Pulse addressing
----------------

``Pulse.m`` is the momentum class of the *currently populated* state the
pulse should address (e.g. "the state created by the previous pulse"). The
compiler resolves whether that population is in the ground or excited state
from its population walk; if both are populated at the same ``m`` the pulse
is ambiguous and ``Pulse.state`` must be given explicitly.

Set points
----------

The delivery-AOM SUServo set point is global sequence state: it changes ONLY
at :class:`SetPoint` events (where the execution engine also waits for the
servo to recapture) and applies to every pulse until the next one. Each
:class:`SetPoint` declares the Rabi frequency obtained at that set point for
each beam used before the next change; this is compile-time metadata used to
derive the default duration of those pulses (``duration = area / (2 * rabi)``).
Note that scanning the spawned set-point parameter does *not* rescale the
pulse durations - durations are independent parameters.

.. warning::
    A :class:`SetPoint` event COSTS TIME: the timeline advances by the servo
    write plus the settle wait (``clock_delivery_preempt_time``). An
    interferometer must be symmetric about its mirror pulse or it will not
    close, so a ``SetPoint`` on one side of the mirror must be compensated
    on the other side. The cleanest way is a mirrored ``SetPoint`` at the
    corresponding position - re-declaring the current value is fine and
    costs exactly the same time.
"""

import logging
import math
from dataclasses import dataclass
from enum import Enum

from repository.lib.physics.lmt_resonance import EXCITED
from repository.lib.physics.lmt_resonance import GROUND
from repository.lib.physics.lmt_resonance import opll_m_term_hz
from repository.lib.pulse_intent import M_AUTO
from repository.lib.pulse_intent import AddressedState
from repository.lib.pulse_intent import StateEffect

logger = logging.getLogger(__name__)

# Event-kind codes shipped to the kernel. Strings must never be stored in
# kernel data arrays, so event types are encoded as integers.
EVENT_PULSE = 0
EVENT_WAIT = 1
EVENT_CLEAROUT = 2
EVENT_SETPOINT = 3
EVENT_CALLBACK = 4


class SequenceError(ValueError):
    """A declared LMT sequence is invalid."""


# Mapping from the Callback declaration's state_effect strings to the integer
# intent codes recorded at fire time (repository.lib.pulse_intent).
_CALLBACK_STATE_EFFECT_CODES = {
    "none": StateEffect.NONE,
    "flip": StateEffect.FLIP,
    "superpose": StateEffect.SUPERPOSE,
}


class Beam(Enum):
    """Direction of the clock beam used for a pulse."""

    UP = "u"
    DOWN = "d"

    @property
    def sign(self) -> int:
        """+1 for the up beam, -1 for the down beam."""
        return 1 if self is Beam.UP else -1


@dataclass(frozen=True)
class Pulse:
    """A square LMT pulse.

    Args:
        area: Pulse area in units of pi (1.0 = pi pulse, 0.5 = pi/2 pulse).
        beam: Beam direction.
        m: Momentum class of the populated state this pulse addresses.
        state: Internal state (``"g"`` or ``"e"``) of that population. Only
            needed when both internal states are populated at the same ``m``.
        label: Optional tag appended to the generated parameter names.
    """

    area: float
    beam: Beam
    m: int
    state: str | None = None
    label: str = ""

    def __post_init__(self):
        if self.area <= 0:
            raise ValueError(f"Pulse area must be positive, got {self.area}")
        if self.state not in (None, GROUND, EXCITED):
            raise ValueError(f"Pulse state must be 'g' or 'e', got {self.state!r}")


@dataclass(frozen=True)
class Wait:
    """A dark time.

    Exactly one of ``t`` and ``param`` must be given. ``t`` spawns a dedicated
    scannable duration parameter with that default; ``param`` names an
    existing ``FloatParamHandle`` attribute on the fragment to reuse instead.
    """

    t: float | None = None
    param: str | None = None
    label: str = ""

    def __post_init__(self):
        if (self.t is None) == (self.param is None):
            raise ValueError("Wait requires exactly one of 't' or 'param'")
        if self.t is not None and self.t < 0:
            raise ValueError(f"Wait time must be non-negative, got {self.t}")


@dataclass(frozen=True)
class Clearout:
    """A 461 nm clearout pulse removing all ground-state population.

    Args:
        duration: Default duration for a dedicated parameter. ``None`` reuses
            the fragment's shared ``clearout_duration`` parameter.
    """

    duration: float | None = None
    label: str = ""


@dataclass(frozen=True)
class SetPoint:
    """Change the delivery-AOM SUServo set point from here on.

    The delivery AOM is one physical device, so the set point is global
    sequence state: it changes ONLY at :class:`SetPoint` events and applies
    to every pulse until the next one. The execution engine writes the new
    set point at the event's position in the timeline and then waits for the
    servo to recapture (the fragment's ``clock_delivery_preempt_time``
    parameter), so no extra settling ``Wait`` is needed.

    .. warning::
        This means a ``SetPoint`` is NOT free: it advances the timeline by
        the servo write plus the settle wait. If you put one between an
        interferometer's beam splitters, the dark times become asymmetric
        and the interferometer will not close unless you compensate on the
        other side of the mirror pulse - ideally with a mirrored
        ``SetPoint`` at the corresponding position (re-declaring the
        current value is fine and costs exactly the same time).

    Because the up and down beams reach the atoms with different efficiency,
    they have different Rabi frequencies at the same delivery power: declare
    the Rabi frequency for each beam you intend to use before the next
    :class:`SetPoint`. These set the default durations of those pulses
    (``duration = area / (2 * rabi)``); a pulse on a beam with no declared
    Rabi at the current set point is a compile error. Note that scanning the
    spawned set-point parameter does *not* rescale the pulse durations -
    durations are their own parameters.

    Args:
        setpoint: Delivery SUServo set point in volts (spawns a scannable
            parameter with this default).
        rabi_up: Rabi frequency in Hz of up-beam pulses at this set point.
        rabi_down: Rabi frequency in Hz of down-beam pulses at this set point.
        label: Optional tag appended to the generated parameter name and
            description.
    """

    setpoint: float
    rabi_up: float | None = None
    rabi_down: float | None = None
    label: str = ""

    def __post_init__(self):
        if self.setpoint < 0:
            raise ValueError(f"Set point must be non-negative, got {self.setpoint}")
        if self.rabi_up is None and self.rabi_down is None:
            raise ValueError(
                "SetPoint must declare the Rabi frequency for at least one beam"
            )
        for name, value in (("rabi_up", self.rabi_up), ("rabi_down", self.rabi_down)):
            if value is not None and value <= 0:
                raise ValueError(f"{name} must be positive, got {value}")

    def rabi_for(self, beam: Beam) -> "float | None":
        return self.rabi_up if beam is Beam.UP else self.rabi_down


@dataclass(frozen=True)
class Callback:
    """Escape hatch: dispatch to a kernel method provided by the subclass.

    The event itself is not expressed in the sequence language; the kernel
    calls ``self.lmt_sequence_callback(callback_id)``, which the experiment
    class overrides with an ``if``/``elif`` dispatch on the id (e.g. to fire
    a shaped pulse). The declared effect on the atoms keeps the compiler's
    population bookkeeping - and therefore the resonance prediction of all
    subsequent pulses - correct.

    Args:
        callback_id: Integer id passed to ``lmt_sequence_callback``.
        delta_m: Momentum change applied to every populated state.
        state_effect: ``"none"`` (internal states unchanged), ``"flip"``
            (ground <-> excited) or ``"superpose"`` (populate both).
        duration: Nominal duration in seconds, for documentation only (the
            callback advances the timeline however it likes).
        label: Optional tag for documentation.
    """

    # FIXME This needs to be more expressive

    callback_id: int
    delta_m: int = 0
    state_effect: str = "none"
    duration: float = 0.0
    label: str = ""

    def __post_init__(self):
        if self.state_effect not in ("none", "flip", "superpose"):
            raise ValueError(
                "Callback state_effect must be 'none', 'flip' or 'superpose', "
                f"got {self.state_effect!r}"
            )


def pi(beam: Beam, m: int, state: str | None = None, label: str = "") -> Pulse:
    """A pi pulse addressing momentum class ``m``."""
    return Pulse(area=1.0, beam=beam, m=m, state=state, label=label)


def pi2(beam: Beam, m: int, state: str | None = None, label: str = "") -> Pulse:
    """A pi/2 pulse addressing momentum class ``m``."""
    return Pulse(area=0.5, beam=beam, m=m, state=state, label=label)


def ladder(start_m: int, n: int, first_beam: Beam) -> list[Pulse]:
    """An alternating-beam ladder of ``n`` pi pulses.

    Pulse ``j`` addresses momentum class ``start_m + j`` with the beams
    alternating from ``first_beam``, transferring one recoil per pulse - the
    standard LMT launch / beam-splitter ladder.
    """
    second = Beam.DOWN if first_beam is Beam.UP else Beam.UP
    return [
        pi(first_beam if j % 2 == 0 else second, m=start_m + j) for j in range(int(n))
    ]


@dataclass(frozen=True)
class ParamSpec:
    """Specification of one ndscan FloatParam to spawn for an event."""

    attr_name: str
    description: str
    default: float
    unit: str
    min: float | None = None


@dataclass(frozen=True)
class CompiledEvent:
    """One sequence event, compiled for execution.

    ``offset_param``, ``duration_param`` and ``setpoint_param`` describe
    parameters the execution mixin must spawn; ``duration_param_ref`` instead
    names an existing handle attribute to reuse for the duration slot.
    ``governing_setpoint_index`` points pulses at the sequence index of the
    :class:`SetPoint` event whose parameter governs their delivery set point.

    ``state_effect``, ``addressed_state``, ``addressed_m`` and ``delta_m``
    carry the event's *intent* - what it is meant to do to the atomic
    populations - encoded with the integer codes of
    :mod:`repository.lib.pulse_intent`. For pulses these are filled by
    :func:`_compile_pulse` from the resolved transition (``EFFECT_FLIP`` for a
    pi pulse, ``EFFECT_SUPERPOSE`` otherwise); for :class:`Callback` events
    they come from the declaration. ``declared_duration_s`` is the
    :class:`Callback`'s nominal duration (0.0 for everything else).
    """

    index: int
    kind: int
    beam_sign: int = 0
    m_term_hz: float = 0.0
    #: Declared Rabi frequency (Hz) of this pulse at its governing delivery set
    #: point, used by the execution engine for the probe (AC-Stark) shift
    #: ``alpha * rabi**2``. 0.0 for non-pulse events.
    rabi_hz: float = 0.0
    callback_id: int = -1
    governing_setpoint_index: int = -1
    offset_param: ParamSpec | None = None
    duration_param: ParamSpec | None = None
    duration_param_ref: str | None = None
    setpoint_param: ParamSpec | None = None
    addressed_pair: tuple | None = None
    state_effect: StateEffect = StateEffect.NONE
    addressed_state: AddressedState = AddressedState.AUTO
    addressed_m: int = M_AUTO
    delta_m: int = 0
    declared_duration_s: float = 0.0


@dataclass(frozen=True)
class CompiledSequence:
    """Result of :func:`compile_sequence`."""

    events: list[CompiledEvent]
    final_population: frozenset

    def __iter__(self):
        return iter(self.events)

    def __len__(self):
        return len(self.events)


def _format_state(state: tuple) -> str:
    return f"|{state[0]}, m={state[1]}>"


def _slug(text: str) -> str:
    """Sanitise free text for use inside a Python identifier."""
    cleaned = "".join(c if c.isalnum() else "_" for c in text).strip("_")
    return cleaned


def _m_tag(m: int) -> str:
    return f"m{m}" if m >= 0 else f"mn{abs(m)}"


def _pulse_tag(event: Pulse) -> str:
    if math.isclose(event.area, 1.0):
        area_tag = "pi"
    elif math.isclose(event.area, 0.5):
        area_tag = "pi2"
    else:
        area_tag = "a" + _slug(f"{event.area:g}".replace(".", "p"))
    return f"{area_tag}_{event.beam.value}_{_m_tag(event.m)}"


def _event_name(index: int, stem: str, label: str = "") -> str:
    name = f"p{index:02d}_{stem}"
    if label:
        name += f"_{_slug(label)}"
    return name


def _event_prefix(index: int, label: str = "") -> str:
    """Human-readable event prefix for parameter descriptions, including the
    user's label so the parameter is recognisable in the ndscan UI."""
    prefix = f"Event {index}"
    if label:
        prefix += f" '{label}'"
    return prefix


def compile_sequence(
    events: list,
    *,
    initial_population: set,
    strict: bool = True,
) -> CompiledSequence:
    """Validate a declared sequence and compile it for execution.

    Walks the sequence tracking the set of populated
    ``(internal_state, momentum_class)`` tuples and the per-beam delivery set
    points, raising :class:`SequenceError` (or warning, where ``strict=False``
    permits) on inconsistencies:

    - a pulse addressing a momentum class with no population,
    - a pulse whose addressed population is ambiguous (both internal states
      populated at the same ``m`` and no explicit ``Pulse.state``),
    - a pulse on a beam with no preceding :class:`SetPoint`,
    - a :class:`Clearout` that would remove all remaining population.

    Args:
        events: List of event dataclasses declared by the experiment.
        initial_population: Set of ``(state, m)`` tuples populated when the
            sequence starts, e.g. ``{("e", 1)}`` after the shelving kick.
        strict: If False, "addresses unpopulated class" errors become
            warnings (an explicit ``Pulse.state`` is then required to resolve
            the transition).

    Returns:
        A :class:`CompiledSequence` with one :class:`CompiledEvent` per input
        event and the final population (useful for asserting that an
        interferometer closes).
    """
    if not events:
        raise SequenceError("The LMT sequence is empty")

    population = {tuple(s) for s in initial_population}
    for state in population:
        if len(state) != 2 or state[0] not in (GROUND, EXCITED):
            raise SequenceError(
                f"Invalid initial population entry {state!r}; expected "
                "('g'|'e', m) tuples"
            )
    if not population:
        raise SequenceError("The initial population is empty")

    # The delivery set point is global state, changed only at SetPoint
    # events: (sequence index of the governing SetPoint, the SetPoint)
    current_setpoint: "tuple[int, SetPoint] | None" = None

    compiled: list[CompiledEvent] = []

    for index, event in enumerate(events):
        if isinstance(event, Pulse):
            compiled.append(
                _compile_pulse(index, event, population, current_setpoint, strict)
            )
        elif isinstance(event, Wait):
            if event.param is not None:
                compiled.append(
                    CompiledEvent(
                        index=index,
                        kind=EVENT_WAIT,
                        duration_param_ref=event.param,
                    )
                )
            else:
                compiled.append(
                    CompiledEvent(
                        index=index,
                        kind=EVENT_WAIT,
                        duration_param=ParamSpec(
                            attr_name=_event_name(index, "wait", event.label)
                            + "_duration",
                            description=f"{_event_prefix(index, event.label)}: "
                            "dark time",
                            default=event.t,
                            unit="us",
                            min=0.0,
                        ),
                    )
                )
        elif isinstance(event, Clearout):
            ground_states = {s for s in population if s[0] == GROUND}
            if ground_states == population:
                message = (
                    f"Event {index}: clearout would remove all remaining "
                    f"population ({', '.join(map(_format_state, sorted(population)))})"
                )
                if strict:
                    raise SequenceError(message)
                logger.warning(message)
            population -= ground_states
            if event.duration is not None:
                compiled.append(
                    CompiledEvent(
                        index=index,
                        kind=EVENT_CLEAROUT,
                        duration_param=ParamSpec(
                            attr_name=_event_name(index, "clearout", event.label)
                            + "_duration",
                            description=f"{_event_prefix(index, event.label)}: "
                            "clearout pulse duration",
                            default=event.duration,
                            unit="us",
                            min=0.0,
                        ),
                    )
                )
            else:
                compiled.append(
                    CompiledEvent(
                        index=index,
                        kind=EVENT_CLEAROUT,
                        duration_param_ref="clearout_duration",
                    )
                )
        elif isinstance(event, SetPoint):
            current_setpoint = (index, event)
            rabi_bits = []
            if event.rabi_up is not None:
                rabi_bits.append(f"up {event.rabi_up / 1e3:.3g} kHz")
            if event.rabi_down is not None:
                rabi_bits.append(f"down {event.rabi_down / 1e3:.3g} kHz")
            compiled.append(
                CompiledEvent(
                    index=index,
                    kind=EVENT_SETPOINT,
                    setpoint_param=ParamSpec(
                        attr_name=_event_name(index, "setpoint", event.label),
                        description=(
                            f"{_event_prefix(index, event.label)}: delivery AOM "
                            "set point from here until the next SetPoint "
                            f"(declared Rabi: {', '.join(rabi_bits)})"
                        ),
                        default=event.setpoint,
                        unit="V",
                        min=0.0,
                    ),
                )
            )
        elif isinstance(event, Callback):
            population = _apply_callback(population, event)
            compiled.append(
                CompiledEvent(
                    index=index,
                    kind=EVENT_CALLBACK,
                    callback_id=event.callback_id,
                    state_effect=_CALLBACK_STATE_EFFECT_CODES[event.state_effect],
                    delta_m=event.delta_m,
                    declared_duration_s=event.duration,
                )
            )
        else:
            raise SequenceError(
                f"Event {index}: unknown sequence event type {type(event).__name__}"
            )

    return CompiledSequence(events=compiled, final_population=frozenset(population))


def _compile_pulse(
    index: int,
    event: Pulse,
    population: set,
    current_setpoint: "tuple[int, SetPoint] | None",
    strict: bool,
) -> CompiledEvent:
    """Resolve, validate and compile a single Pulse, updating ``population``."""
    if current_setpoint is None:
        raise SequenceError(
            f"Event {index}: pulse before any SetPoint - the sequence must "
            "declare the delivery set point first"
        )
    setpoint_index, setpoint = current_setpoint
    rabi_frequency = setpoint.rabi_for(event.beam)
    if rabi_frequency is None:
        raise SequenceError(
            f"Event {index}: pulse on the {event.beam.name.lower()} beam, but "
            f"the governing SetPoint (event {setpoint_index}) declares no "
            f"rabi_{event.beam.name.lower()} - declare the Rabi frequency of "
            "this beam at the current set point"
        )

    # Resolve which internal state this pulse addresses
    populated_states = [s for s in (GROUND, EXCITED) if (s, event.m) in population]
    if event.state is not None:
        if event.state not in populated_states:
            message = (
                f"Event {index}: pulse addresses {_format_state((event.state, event.m))} "
                f"but it is not populated (populated: "
                f"{', '.join(map(_format_state, sorted(population)))})"
            )
            if strict:
                raise SequenceError(message)
            logger.warning(message)
            # The user is overriding the walker's bookkeeping: trust the
            # declared state and track the pulse's effect from there.
            population.add((event.state, event.m))
        input_state = event.state
    elif len(populated_states) == 1:
        input_state = populated_states[0]
    elif len(populated_states) == 2:
        raise SequenceError(
            f"Event {index}: both |g, m={event.m}> and |e, m={event.m}> are "
            "populated - give Pulse(..., state='g' or 'e') to disambiguate"
        )
    else:
        # No population at this m and no explicit state: the transition is
        # unresolvable, so this is an error even with strict=False.
        raise SequenceError(
            f"Event {index}: pulse addresses m={event.m} but no population is "
            f"there (populated: {', '.join(map(_format_state, sorted(population)))})"
            " - give Pulse(..., state='g' or 'e') to fire it anyway"
        )

    s = event.beam.sign
    m_term = opll_m_term_hz(event.m, input_state, s)

    # The addressed pair |g, m_g> <-> |e, m_g + s>
    if input_state == GROUND:
        m_g = event.m
    else:
        m_g = event.m - s
    ground = (GROUND, m_g)
    excited = (EXCITED, m_g + s)

    # Update the population walk: a pi pulse swaps the populated sides of the
    # pair; any other area populates both sides.
    had_ground = ground in population
    had_excited = excited in population
    population.discard(ground)
    population.discard(excited)
    if math.isclose(event.area, 1.0):
        if had_ground:
            population.add(excited)
        if had_excited:
            population.add(ground)
    else:
        if had_ground or had_excited:
            population.add(ground)
            population.add(excited)

    tag = _pulse_tag(event)
    name = _event_name(index, tag, event.label)
    duration_default = event.area / (2.0 * rabi_frequency)
    if math.isclose(event.area, 1.0):
        area_text = "pi"
    elif math.isclose(event.area, 0.5):
        area_text = "pi/2"
    else:
        area_text = f"{event.area:g} pi"
    human = (
        f"{area_text} {event.beam.name.lower()}-beam pulse addressing "
        f"{_format_state((input_state, event.m))}"
    )

    return CompiledEvent(
        index=index,
        kind=EVENT_PULSE,
        beam_sign=s,
        m_term_hz=m_term,
        # Intensity-derived Rabi frequency declared for this beam at the
        # governing set point; the execution engine uses it for the probe
        # (AC-Stark) shift. Scanning the pulse duration does NOT change this,
        # because the light shift tracks the delivery intensity (the set
        # point), not the pulse length.
        rabi_hz=rabi_frequency,
        governing_setpoint_index=setpoint_index,
        # Intent: a pi pulse swaps the addressed pair's populations; any
        # other area populates both sides. delta_m is the beam sign (recoils
        # given in the ground->excited direction).
        state_effect=(
            StateEffect.FLIP if math.isclose(event.area, 1.0) else StateEffect.SUPERPOSE
        ),
        addressed_state=(
            AddressedState.GROUND if input_state == GROUND else AddressedState.EXCITED
        ),
        addressed_m=event.m,
        delta_m=s,
        offset_param=ParamSpec(
            attr_name=name + "_offset",
            description=(
                f"{_event_prefix(index, event.label)}: {human} - detuning "
                "offset added to the model-predicted resonance"
            ),
            default=0.0,
            unit="kHz",
        ),
        duration_param=ParamSpec(
            attr_name=name + "_duration",
            description=f"{_event_prefix(index, event.label)}: {human} - duration",
            default=duration_default,
            unit="us",
            min=0.0,
        ),
        addressed_pair=(ground, excited),
    )


def _apply_callback(population: set, event: Callback) -> set:
    """Apply a Callback's declared effect to every populated state."""
    new_population = set()
    for state, m in population:
        m_new = m + event.delta_m
        if event.state_effect == "none":
            new_population.add((state, m_new))
        elif event.state_effect == "flip":
            new_population.add((EXCITED if state == GROUND else GROUND, m_new))
        else:  # superpose
            new_population.add((GROUND, m_new))
            new_population.add((EXCITED, m_new))
    return new_population
