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
from dataclasses import field
from enum import Enum

from repository.lib.physics.lmt_resonance import EXCITED
from repository.lib.physics.lmt_resonance import GROUND
from repository.lib.physics.lmt_resonance import M_AUTO
from repository.lib.physics.lmt_resonance import AddressedState
from repository.lib.physics.lmt_resonance import InternalState
from repository.lib.physics.lmt_resonance import StateEffect
from repository.lib.physics.lmt_resonance import _ground_class_of_pair
from repository.lib.physics.lmt_resonance import opll_m_term_hz

logger = logging.getLogger(__name__)

# Event-kind codes shipped to the kernel. Strings must never be stored in
# kernel data arrays, so event types are encoded as integers.
EVENT_PULSE = 0
EVENT_WAIT = 1
EVENT_CLEAROUT = 2
EVENT_SETPOINT = 3
EVENT_CALLBACK = 4
EVENT_PHASE = 5


class SequenceError(ValueError):
    """A declared LMT sequence is invalid."""


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
        state: Internal state (:data:`GROUND` or :data:`EXCITED`) of that
            population. Only needed when both internal states are populated at
            the same ``m``.
        label: Optional tag appended to the generated parameter names.
    """

    area: float
    beam: Beam
    m: int
    state: InternalState | None = None
    label: str = ""

    def __post_init__(self):
        if self.area <= 0:
            raise ValueError(f"Pulse area must be positive, got {self.area}")
        if self.state not in (None, GROUND, EXCITED):
            raise ValueError(
                f"Pulse state must be GROUND or EXCITED, got {self.state!r}"
            )


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
class Phase:
    """Set the absolute switch-AOM phase applied to every following pulse.

    The phase is programmed onto both clock switch DDSes (up and down) and, since
    pulses are fired by gating those DDSes on and off without reprogramming them,
    persists until the next :class:`Phase` event. It is zero-duration and has no
    effect on the atomic populations (so the trajectory is unchanged); it only
    rotates the phase the subsequent pulses are emitted with. Exactly one of
    ``phase`` and ``param`` must be given. ``phase`` spawns a dedicated
    scannable parameter with that default; ``param`` names an existing
    ``FloatParamHandle`` attribute on the fragment to reuse instead - the
    value read from it is scaled by ``multiplier`` before being applied, so
    one shared phase handle can drive several :class:`Phase` events with
    different (static) scale factors, e.g. a mirror pulse needing twice the
    beam splitters' phase.

    Args:
        phase: Absolute AOM phase in turns (1.0 = one full turn = 2*pi).
        param: Name of an existing ``FloatParamHandle`` attribute to reuse
            instead of spawning a dedicated parameter.
        multiplier: Static scale factor applied to the value read from
            ``param`` (irrelevant when ``phase`` is given instead).
        label: Optional tag appended to the generated parameter name.
    """

    phase: float | None = None
    param: str | None = None
    multiplier: float = 1.0
    label: str = ""

    def __post_init__(self):
        if (self.phase is None) == (self.param is None):
            raise ValueError("Phase requires exactly one of 'phase' or 'param'")
        if self.param is None and self.multiplier != 1.0:
            raise ValueError(
                "Phase multiplier only has an effect together with 'param' "
                "(there is no shared handle to scale)"
            )


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
    Rabi at the current set point is a compile error.

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
class CallbackAction:
    """One elementary addressed-action of a :class:`Callback`.

    Describes what a callback does to a single addressed momentum class
    ``(state, m)``, exactly as an ordinary pulse intent row would (see
    :mod:`repository.lib.physics.lmt_resonance`). The pairing rule is the shared
    one: ``delta_m`` plays the beam sign, so the action addresses the pair
    ``|g, m_g> <-> |e, m_g + delta_m>``.

    Args:
        state: Internal state (:data:`GROUND` or :data:`EXCITED`) of the
            addressed population.
        m: Momentum class of the addressed population.
        delta_m: Recoils given in the ground->excited direction (the
            excited->ground direction gets the negative); plays the beam sign
            for the pairing.
        state_effect: :data:`StateEffect.FLIP` (swap the pair's populated
            side), :data:`StateEffect.SUPERPOSE` (populate both) or
            :data:`StateEffect.NONE` (pure momentum kick, internal state
            unchanged).
    """

    state: InternalState
    m: int
    delta_m: int
    state_effect: StateEffect = StateEffect.FLIP


@dataclass(frozen=True)
class Callback:
    """Escape hatch: dispatch to a kernel method provided by the subclass.

    The event itself is not expressed in the sequence language; the kernel
    calls ``self.lmt_sequence_callback_hook(callback_id)``, which the
    experiment class overrides with an ``if``/``elif`` dispatch on the id (e.g.
    to fire a shaped pulse). The declared effect on the atoms keeps the
    compiler's population bookkeeping - and therefore the resonance prediction
    of all subsequent pulses - correct.

    The effect on the atoms is modelled as an explicit list of elementary
    :class:`CallbackAction` items, all taken to act at one instant. Each action
    is treated exactly like an ordinary declarative pulse - the trackers model
    no off-resonant excitation, so every action (like every pulse) addresses
    only its own ``(state, m)`` pair. What a callback adds over a single pulse
    is therefore just what one clock pulse cannot express at one timestamp:
    **several simultaneous actions** (e.g. push m up and m-1 down at once), a
    **pure momentum kick** (:data:`StateEffect.NONE`, no internal-state flip),
    or **no atomic effect at all**. At fire time the callback emits one ordinary
    pulse intent row per action, sharing one ``t_start``; the analysis consumers
    therefore see a callback as N ordinary pulse rows and need no
    callback-specific logic.

    The action list may be **empty**: a callback that only triggers external
    hardware and touches no atoms. It leaves NO intent record and makes NO
    change to the population walk.

    Args:
        callback_id: Integer id passed to ``lmt_sequence_callback_hook``.
        actions: List of :class:`CallbackAction` describing the addressed
            momentum classes and what happens to each. Empty for a pure
            external trigger.
        duration: Nominal duration in seconds, for documentation only (the
            callback advances the timeline however it likes).
        label: Optional tag for documentation.
    """

    callback_id: int
    actions: list = field(default_factory=list)
    duration: float = 0.0
    label: str = ""


def pi(
    beam: Beam, m: int, state: InternalState | None = None, label: str = ""
) -> Pulse:
    """A pi pulse addressing momentum class ``m``."""
    return Pulse(area=1.0, beam=beam, m=m, state=state, label=label)


def pi2(
    beam: Beam, m: int, state: InternalState | None = None, label: str = ""
) -> Pulse:
    """A pi/2 pulse addressing momentum class ``m``."""
    return Pulse(area=0.5, beam=beam, m=m, state=state, label=label)


def ladder(
    start_m: int,
    n: int,
    first_beam: Beam,
    direction: int = 1,
    clearout_from: int | None = None,
) -> list:
    """An alternating-beam ladder of ``n`` pi pulses.

    Pulse ``j`` addresses momentum class ``start_m + j * direction`` -
    transferring one recoil per pulse in that direction, the standard LMT
    launch / beam-splitter ladder. ``direction`` must be +1 (climbing the
    ladder, the default) or -1 (descending it).

    ``first_beam`` names the beam that climbs the ladder from the entering
    internal state (as for ``direction=1``); descending it (``direction=-1``)
    requires the opposite beam at each step (c.f. ``_raise_arm``/
    ``_lower_arm``), so the beam sequence used is transparently inverted
    when ``direction=-1`` - callers do not need to flip ``first_beam``
    themselves when reusing the same ladder shape in reverse.

    ``clearout_from`` inserts a :class:`Clearout` after every pulse that leaves
    the packet in the excited state - removing residual ground-state population
    between launch steps. Since the up beam climbs from the ground state and the
    down beam from the excited state, the entering state (and hence which pulses
    leave the packet excited) is fixed by ``first_beam``. A non-negative value
    clears out from pulse ``clearout_from`` onwards (pulse 0 being the first); a
    negative value counts from the end, e.g. ``-2`` clears out over the final
    two pulses. The default of ``None`` inserts no clearouts.
    """
    if direction not in (1, -1):
        raise ValueError(f"ladder direction must be +1 or -1, got {direction}")

    n = int(n)
    clearout_threshold = None
    if clearout_from is not None:
        clearout_threshold = clearout_from if clearout_from >= 0 else n + clearout_from

    # The entering internal state is fixed by first_beam as passed (as for
    # direction=+1): the up beam climbs from ground, the down beam from excited.
    entering_excited = first_beam is Beam.DOWN

    if direction == -1:
        first_beam = Beam.DOWN if first_beam is Beam.UP else Beam.UP
    second = Beam.DOWN if first_beam is Beam.UP else Beam.UP

    events: list = []
    for j in range(n):
        events.append(
            pi(first_beam if j % 2 == 0 else second, m=start_m + j * direction)
        )
        # Each pi pulse flips the internal state, so after pulse j the packet
        # has flipped j+1 times.
        packet_excited = entering_excited ^ ((j + 1) % 2 == 1)
        if (
            clearout_threshold is not None
            and j >= clearout_threshold
            and packet_excited
        ):
            events.append(Clearout())
    return events


@dataclass(frozen=True)
class Arm:
    """One arm of the interferometer: an atomic state and momentum class."""

    state: InternalState
    m: int


def _raise_arm(arm: Arm) -> "tuple[Pulse, Arm]":
    """A pi pulse that raises one arm's momentum class by one recoil.

    Returns the pulse and the arm's new state. The beam is chosen so the recoil
    is delivered upward (up beam on ground, down beam on excited).
    """
    if arm.state == GROUND:
        return pi(Beam.UP, m=arm.m, state=GROUND), Arm(EXCITED, arm.m + 1)
    return pi(Beam.DOWN, m=arm.m, state=EXCITED), Arm(GROUND, arm.m + 1)


def _lower_arm(arm: Arm) -> "tuple[Pulse, Arm]":
    """A pi pulse that lowers one arm's momentum class by one recoil."""
    if arm.state == GROUND:
        return pi(Beam.DOWN, m=arm.m, state=GROUND), Arm(EXCITED, arm.m - 1)
    return pi(Beam.UP, m=arm.m, state=EXCITED), Arm(GROUND, arm.m - 1)


def symmetric_mach_zehnder_sequence(
    *,
    n_launch: int,
    n_recoils: int,
    slice_setpoint: float,
    slice_rabi_up: float,
    full_setpoint: float,
    rabi_up: float,
    rabi_down: float,
    dark_param_1: str = "lmt_dark_time_1",
    dark_param_2: str = "lmt_dark_time_2",
    phase_param: str = "lmt_interferometry_phase",
) -> list:
    """Build the canonical velocity-selected launch + symmetric LMT Mach-Zehnder
    sequence.

    Procedurally generates the declarative event list for the standard
    interferometer from a handful of counts, so the whole sequence is driven by
    global parameters instead of one parameter per pulse. The atoms start in
    ``{('g', 0)}`` (release from the trap); the structure is:

    1. velocity selection (a low-set-point up-beam pi pulse),
    2. a launch ladder of ``n_launch`` alternating pi pulses to ``m = 1 +
       n_launch``,
    3. a beam splitter, then ``n_recoils`` symmetric augmentation pulses that
       separate the two arms to ``1 + 2 * n_recoils`` recoils for the dark time,
       brought back to an adjacent pair around the single-pi mirror, repeated
       symmetrically after the mirror, and finally the recombiner.

    The arms are maximally separated during the (equal) dark times and adjacent
    at the mirror and beam splitters, so the interferometer closes to a single
    momentum pair for any ``n_launch``/``n_recoils`` (verified by the compiler's
    population walk). The augmentation geometry is the idealised-closure
    baseline; the per-beam detunings, durations, set points and dark times are
    bound to shared global handles by the execution mixin.

    Args:
        n_launch: Number of launch ladder pulses (set once per run).
        n_recoils: Number of LMT-enhanced recoils added to each arm in each
            half of the interferometer (set once per run; 0 is a plain 1-recoil
            Mach-Zehnder).
        slice_setpoint: Delivery set point declared for the slice SetPoint.
        slice_rabi_up: Up-beam Rabi frequency declared at the slice set point.
        full_setpoint: Delivery set point declared for the launch/interferometer.
        rabi_up: Up-beam Rabi frequency declared at the full set point.
        rabi_down: Down-beam Rabi frequency declared at the full set point.
        dark_param_1: Fragment attribute name of the first dark-time parameter.
        dark_param_2: Fragment attribute name of the second dark-time parameter.
        phase_param: Fragment attribute name of the interferometry phase parameter.

    Returns:
        A list of event dataclasses suitable for :func:`compile_sequence` with
        ``initial_population={('g', 0)}``.
    """
    if n_launch < 0:
        raise ValueError(f"n_launch must be non-negative, got {n_launch}")
    if n_recoils < 0:
        raise ValueError(f"n_recoils must be non-negative, got {n_recoils}")

    m_top = 1 + n_launch
    sequence: list = [
        SetPoint(setpoint=slice_setpoint, rabi_up=slice_rabi_up, label="slice"),
        pi(Beam.UP, m=0, label="slice"),
        SetPoint(setpoint=full_setpoint, rabi_up=rabi_up, rabi_down=rabi_down),
        Clearout(label="post_slice"),
        *ladder(start_m=1, n=n_launch, first_beam=Beam.DOWN),
    ]

    # The slice leaves (e, 1); each launch pulse flips the internal state, so
    # the launched packet is excited only for an even launch count. The
    # post-launch clearout removes residual ground atoms, which is only possible
    # (and meaningful) when the packet itself is excited.
    packet_excited = n_launch % 2 == 0
    if packet_excited:
        sequence.append(Clearout(label="post_launch"))

    sequence.append(pi2(Beam.DOWN, m=m_top, label="bs1"))
    if packet_excited:
        # bs1 on (e, m_top) populates the pair (e, m_top) <-> (g, m_top + 1)
        arm_lo, arm_hi = Arm(EXCITED, m_top), Arm(GROUND, m_top + 1)
    else:
        # bs1 on (g, m_top) populates the pair (g, m_top) <-> (e, m_top - 1)
        arm_lo, arm_hi = Arm(EXCITED, m_top - 1), Arm(GROUND, m_top)

    def separate():
        nonlocal arm_hi, arm_lo
        for _ in range(n_recoils):
            pulse, arm_hi = _raise_arm(arm_hi)
            sequence.append(pulse)
            pulse, arm_lo = _lower_arm(arm_lo)
            sequence.append(pulse)

    def rejoin():
        nonlocal arm_hi, arm_lo
        for _ in range(n_recoils):
            pulse, arm_hi = _lower_arm(arm_hi)
            sequence.append(pulse)
            pulse, arm_lo = _raise_arm(arm_lo)
            sequence.append(pulse)

    separate()
    sequence.append(Phase(param=phase_param, multiplier=1.0, label="mirror"))
    sequence.append(Wait(param=dark_param_1, label="dark1"))
    rejoin()
    sequence.append(pi(Beam.DOWN, m=min(arm_hi.m, arm_lo.m) + 1, label="mirror"))
    separate()
    sequence.append(Phase(param=phase_param, multiplier=4.0, label="bs2"))
    sequence.append(Wait(param=dark_param_2, label="dark2"))
    rejoin()
    sequence.append(pi2(Beam.DOWN, m=min(arm_hi.m, arm_lo.m) + 1, label="bs2"))
    return sequence


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
    parameters the execution mixin must spawn; ``duration_param_ref`` and
    ``phase_param_ref`` instead name an existing handle attribute to reuse for
    the duration/phase slot. ``phase_multiplier`` is the static scale factor
    applied to the value read from a ``phase_param_ref`` handle (see
    :class:`Phase`).
    ``governing_setpoint_index`` points pulses at the sequence index of the
    :class:`SetPoint` event whose parameter governs their delivery set point.

    ``state_effect``, ``addressed_state``, ``addressed_m`` and ``delta_m``
    carry a *pulse* event's *intent* - what it is meant to do to the atomic
    populations - encoded with the integer codes of
    :mod:`repository.lib.physics.lmt_resonance`. They are filled by
    :func:`_compile_pulse` from the resolved transition (``EFFECT_FLIP`` for a
    pi pulse, ``EFFECT_SUPERPOSE`` otherwise).

    ``callback_actions`` carries a :class:`Callback`'s declared actions, each
    encoded as an integer 4-tuple
    ``(addressed_state, addressed_m, delta_m, state_effect)`` where
    ``addressed_state`` is an :class:`AddressedState` code. At fire time each
    action is registered as one ordinary pulse intent row, so a callback
    contributes N pulse-like columns to the on-disk record.
    ``declared_duration_s`` is the :class:`Callback`'s nominal duration (0.0
    for everything else).
    """

    index: int
    kind: int
    beam_sign: int = 0
    m_term_hz: float = 0.0
    rabi_hz: float = 0.0
    callback_id: int = -1
    governing_setpoint_index: int = -1
    offset_param: ParamSpec | None = None
    duration_param: ParamSpec | None = None
    duration_param_ref: str | None = None
    setpoint_param: ParamSpec | None = None
    phase_param: ParamSpec | None = None
    phase_param_ref: str | None = None
    phase_multiplier: float = 1.0
    addressed_pair: tuple | None = None
    state_effect: StateEffect = StateEffect.NONE
    addressed_state: AddressedState = AddressedState.AUTO
    addressed_m: int = M_AUTO
    delta_m: int = 0
    declared_duration_s: float = 0.0
    callback_actions: tuple = ()


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
    return f"|{state[0].value}, m={state[1]}>"


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
                            f"{_event_prefix(index, event.label)}: delivery setpoint"
                        ),
                        default=event.setpoint,
                        unit="V",
                        min=0.0,
                    ),
                )
            )
        elif isinstance(event, Phase):
            # A pure phase change: no population or set-point side effect, and
            # allowed anywhere (even before the first SetPoint).
            if event.param is not None:
                compiled.append(
                    CompiledEvent(
                        index=index,
                        kind=EVENT_PHASE,
                        phase_param_ref=event.param,
                        phase_multiplier=event.multiplier,
                    )
                )
            else:
                assert event.phase is not None
                compiled.append(
                    CompiledEvent(
                        index=index,
                        kind=EVENT_PHASE,
                        phase_param=ParamSpec(
                            attr_name=_event_name(index, "phase", event.label),
                            description=(
                                f"{_event_prefix(index, event.label)}: switch AOM "
                                "phase (turns)"
                            ),
                            default=event.phase,
                            unit="",
                        ),
                    )
                )
        elif isinstance(event, Callback):
            _apply_callback(population, event)
            actions = tuple(
                (
                    int(
                        AddressedState.GROUND
                        if action.state == GROUND
                        else AddressedState.EXCITED
                    ),
                    int(action.m),
                    int(action.delta_m),
                    int(action.state_effect),
                )
                for action in event.actions
            )
            compiled.append(
                CompiledEvent(
                    index=index,
                    kind=EVENT_CALLBACK,
                    callback_id=event.callback_id,
                    declared_duration_s=event.duration,
                    callback_actions=actions,
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
            f"Event {index} {event.label}: pulse on the {event.beam.name.lower()} beam, but "
            f"the governing SetPoint (event {setpoint_index}) declares no "
            f"rabi_{event.beam.name.lower()} - declare the Rabi frequency of "
            "this beam at the current set point"
        )

    # Resolve which internal state this pulse addresses
    populated_states = [s for s in (GROUND, EXCITED) if (s, event.m) in population]
    if event.state is not None:
        if event.state not in populated_states:
            message = (
                f"Event {index} {event.label}: pulse addresses {_format_state((event.state, event.m))} "
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
            f"Event {index} {event.label}: both |g, m={event.m}> and |e, m={event.m}> are "
            "populated - give Pulse(..., state=GROUND or EXCITED) to disambiguate"
        )
    else:
        # No population at this m and no explicit state: the transition is
        # unresolvable, so this is an error even with strict=False.
        raise SequenceError(
            f"Event {index} {event.label}: pulse addresses m={event.m} but no population is "
            f"there (populated: {', '.join(map(_format_state, sorted(population)))})"
            " - give Pulse(..., state=GROUND or EXCITED) to fire it anyway"
        )

    s = event.beam.sign
    m_term = opll_m_term_hz(event.m, input_state, s)

    # The addressed pair |g, m_g> <-> |e, m_g + s>
    m_g = _ground_class_of_pair(event.m, input_state == GROUND, s)
    ground = (GROUND, m_g)
    excited = (EXCITED, m_g + s)

    # Update the population walk: a pi pulse swaps the populated sides of the
    # pair; any other area populates both sides.
    pulse_effect = (
        StateEffect.FLIP if math.isclose(event.area, 1.0) else StateEffect.SUPERPOSE
    )
    _apply_addressed_action(population, input_state, event.m, s, pulse_effect)

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
        rabi_hz=rabi_frequency,
        governing_setpoint_index=setpoint_index,
        # Intent: a pi pulse swaps the addressed pair's populations; any
        # other area populates both sides. delta_m is the beam sign (recoils
        # given in the ground->excited direction).
        state_effect=pulse_effect,
        addressed_state=(
            AddressedState.GROUND if input_state == GROUND else AddressedState.EXCITED
        ),
        addressed_m=event.m,
        delta_m=s,
        offset_param=ParamSpec(
            attr_name=name + "_offset",
            description=f"{_event_prefix(index, event.label)}: {human} - detuning ",
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


def _apply_addressed_action(
    population: set,
    addressed_state: InternalState,
    addressed_m: int,
    delta_m: int,
    state_effect: StateEffect,
) -> None:
    """Apply one elementary addressed-action to ``population`` in place.

    The action addresses the pair ``|g, m_g> <-> |e, m_g + delta_m>`` (the
    pairing rule shared with the intent walkers, ``delta_m`` playing the beam
    sign) and acts exclusively on its two members:

    - :data:`StateEffect.FLIP`: swap the pair's populated side(s),
    - :data:`StateEffect.SUPERPOSE`: populate both members if either was,
    - :data:`StateEffect.NONE`: shift the addressed population's ``m`` by
      ``delta_m`` with its internal state unchanged (a pure momentum kick).

    This is the single source of the compiler's population walk for both pulses
    (:func:`_compile_pulse`) and callback actions (:func:`_apply_callback`), so
    a flattened callback walks identically to the equivalent pulse intent rows
    in :mod:`repository.lib.physics.trajectory`.
    """
    m_g = _ground_class_of_pair(addressed_m, addressed_state == GROUND, delta_m)
    ground = (GROUND, m_g)
    excited = (EXCITED, m_g + delta_m)

    if state_effect == StateEffect.NONE:
        # Pure momentum kick: shift the addressed population by delta_m,
        # internal state unchanged.
        addressed = (addressed_state, addressed_m)
        if addressed in population:
            population.discard(addressed)
            population.add((addressed_state, addressed_m + delta_m))
        return

    had_ground = ground in population
    had_excited = excited in population
    population.discard(ground)
    population.discard(excited)
    if state_effect == StateEffect.FLIP:
        if had_ground:
            population.add(excited)
        if had_excited:
            population.add(ground)
    else:  # SUPERPOSE
        if had_ground or had_excited:
            population.add(ground)
            population.add(excited)


def _apply_callback(population: set, event: Callback) -> None:
    """Apply a Callback's declared actions to ``population`` in place.

    Each :class:`CallbackAction` is applied through the same
    :func:`_apply_addressed_action` helper used for pulses, so the compiler's
    population walk for a callback action is identical to walking the
    equivalent pulse intent row. An empty action list leaves the population
    unchanged.
    """
    for action in event.actions:
        _apply_addressed_action(
            population,
            action.state,
            action.m,
            action.delta_m,
            action.state_effect,
        )
