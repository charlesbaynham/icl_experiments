# FIXME This module seems to completely duplicate the functionality of lmt_resonance.py. We need to consolidate these. Let's go with lmt_resonance as the default choice, it's more complete.


"""
Pulse-intent record vocabulary
==============================

Pure host-side (no ARTIQ) definitions of the *intent* stream recorded by
:class:`~repository.lib.fragments.pulse_recorder_and_tracker.PulseDMARecording`
alongside the pulse facts.

Every event that affects the atoms - clock pulses, 461 nm clearouts and
"callback" pulses (shaped/Jesse pulses fired outside the standard square-pulse
path) - registers one entry describing **what it is meant to do to the atomic
populations, assumed 100 % efficient**, at the moment it fires and next to its
recorded facts. Because facts and intent are appended by the same call, a
skipped or conditional pulse can never misalign the record.

The stream is consumed by the dynamic-ROI trajectory predictor
(:mod:`repository.lib.physics.trajectory`) and archived per shot (deduplicated)
for offline analysis, where it can be checked against the recorded frequency
facts.

Schema
------

One entry per event, in firing order:

==================  =======  ====================================================
field               type     meaning
==================  =======  ====================================================
``t_start_mu``      int64    timeline position when the event starts
``duration_mu``     int64    event duration
``kind``            int32    ``Kind.PULSE``, ``Kind.CLEAROUT`` or
                             ``Kind.CALLBACK``
``state_effect``    int32    ``StateEffect.FLIP`` (pi-like full transfer),
                             ``StateEffect.SUPERPOSE`` (pi/2-like split: both
                             pair members populated) or ``StateEffect.NONE``
``addressed_state`` int32    internal state of the population the event
                             addresses: ``AddressedState.GROUND``,
                             ``AddressedState.EXCITED`` or ``AddressedState.AUTO``
                             (resolve from the population walk)
``addressed_m``     int32    momentum class of the addressed population, or
                             :data:`M_AUTO`
``delta_m``         int32    recoils given to the transferred component in the
                             ground->excited direction (the excited->ground
                             direction gets the negative). For
                             ``Kind.CALLBACK`` with ``state_effect``
                             ``StateEffect.NONE``, applied to every populated
                             branch as-is.
==================  =======  ====================================================

For a plain square clock pulse the default intent is a pi transfer of the
addressed pair with ``delta_m`` equal to the beam sign (+1 up, -1 down) -
exactly the momentum bookkeeping of a resonant pi pulse. Clearouts remove all
ground-state population and carry no momentum fields.
"""

from dataclasses import dataclass
from enum import IntEnum
from typing import Sequence


# ── Event kinds ───────────────────────────────────────────────────────────────
class Kind(IntEnum):
    PULSE = 0
    CLEAROUT = 1
    CALLBACK = 2


# ── State effects ─────────────────────────────────────────────────────────────
class StateEffect(IntEnum):
    FLIP = 0  # pi-like: the addressed pair's population swaps sides
    SUPERPOSE = 1  # pi/2-like: both members of the addressed pair populated
    NONE = 2  # internal states unchanged


# ── Addressed internal state ──────────────────────────────────────────────────
class AddressedState(IntEnum):
    AUTO = -1  # resolve from the population walk
    GROUND = 0
    EXCITED = 1


# ── Momentum-class sentinel ───────────────────────────────────────────────────
#: "Resolve the addressed momentum class from the population walk". Far outside
#: any physical recoil count so it can never collide with a real value.
M_AUTO = -1048576


@dataclass(frozen=True)
class IntentEvent:
    """One decoded entry of the intent stream, with times in seconds.

    Times are in whatever frame the caller rebased them to (the trajectory
    predictor expects seconds since atom release).

    ``kind``/``state_effect``/``addressed_state`` may be given as raw ints or as
    enum members; ``__post_init__`` coerces them to the enums, which also
    validates them (the enum constructor raises ``ValueError`` on an unknown
    code).
    """

    t_start_s: float
    duration_s: float
    kind: Kind
    state_effect: StateEffect
    addressed_state: AddressedState
    addressed_m: int
    delta_m: int

    @property
    def t_centre_s(self) -> float:
        """Instantaneous-kick time: the centre of the event."""
        return self.t_start_s + self.duration_s / 2.0

    def __post_init__(self):
        # Coerce to the enums; an unknown code raises ValueError here. Frozen
        # dataclass, so assign through object.__setattr__.
        object.__setattr__(self, "kind", Kind(self.kind))
        object.__setattr__(self, "state_effect", StateEffect(self.state_effect))
        object.__setattr__(
            self, "addressed_state", AddressedState(self.addressed_state)
        )

    def addresses_pair(self, is_ground: bool, m: int) -> bool:
        """Is the population ``(is_ground, m)`` addressed by this event?

        Shared by the dynamic-ROI predictor
        (:mod:`repository.lib.physics.trajectory`) and the spacetime diagram
        (:mod:`repository.lib.physics.lmt_spacetime`) so they always agree on
        which branches a pulse touches.

        ``AddressedState.AUTO``/``M_AUTO`` (the legacy ``register_pulse``
        default) address every populated branch through the pulse's own
        coupling - correct for the single-chain sequences legacy code fires. An
        explicitly declared pair ``|g, m_g> <-> |e, m_g + delta_m>`` (the
        declarative engine) addresses only its two members, leaving e.g. a
        parked interferometer arm untouched.
        """
        state_auto = self.addressed_state == AddressedState.AUTO
        m_auto = self.addressed_m == M_AUTO

        if state_auto and m_auto:
            return True
        if m_auto:
            # State declared, momentum class automatic: every branch in that state
            return is_ground == (self.addressed_state == AddressedState.GROUND)
        if state_auto:
            # Momentum class declared, state automatic: every branch at that m
            return m == self.addressed_m

        # Both declared: the addressed pair is |g, m_g> <-> |e, m_g + delta_m>,
        # and population on either side of the pair participates.
        if self.addressed_state == AddressedState.GROUND:
            m_g = self.addressed_m
        else:
            m_g = self.addressed_m - self.delta_m
        if is_ground:
            return m == m_g
        return m == m_g + self.delta_m


def intent_events_from_arrays(
    t_start_s: Sequence[float],
    duration_s: Sequence[float],
    kinds: Sequence[int],
    state_effects: Sequence[int],
    addressed_states: Sequence[int],
    addressed_m: Sequence[int],
    delta_m: Sequence[int],
) -> list[IntentEvent]:
    """Assemble parallel record arrays into a list of :class:`IntentEvent`.

    All arrays must have the same length; validation of the field values
    happens in :class:`IntentEvent`.
    """
    n = len(t_start_s)
    for name, arr in (
        ("duration_s", duration_s),
        ("kinds", kinds),
        ("state_effects", state_effects),
        ("addressed_states", addressed_states),
        ("addressed_m", addressed_m),
        ("delta_m", delta_m),
    ):
        if len(arr) != n:
            raise ValueError(
                f"Intent record arrays must have equal lengths: "
                f"t_start_s has {n}, {name} has {len(arr)}"
            )
    return [
        IntentEvent(
            t_start_s=float(t_start_s[i]),
            duration_s=float(duration_s[i]),
            kind=int(kinds[i]),
            state_effect=int(state_effects[i]),
            addressed_state=int(addressed_states[i]),
            addressed_m=int(addressed_m[i]),
            delta_m=int(delta_m[i]),
        )
        for i in range(n)
    ]
