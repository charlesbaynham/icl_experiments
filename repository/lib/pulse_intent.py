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
``kind``            int32    :data:`KIND_PULSE`, :data:`KIND_CLEAROUT` or
                             :data:`KIND_CALLBACK`
``state_effect``    int32    :data:`EFFECT_FLIP` (pi-like full transfer),
                             :data:`EFFECT_SUPERPOSE` (pi/2-like split: both
                             pair members populated) or :data:`EFFECT_NONE`
``addressed_state`` int32    internal state of the population the event
                             addresses: :data:`STATE_GROUND`,
                             :data:`STATE_EXCITED` or :data:`STATE_AUTO`
                             (resolve from the population walk)
``addressed_m``     int32    momentum class of the addressed population, or
                             :data:`M_AUTO`
``delta_m``         int32    recoils given to the transferred component in the
                             ground->excited direction (the excited->ground
                             direction gets the negative). For
                             :data:`KIND_CALLBACK` with ``state_effect``
                             :data:`EFFECT_NONE`, applied to every populated
                             branch as-is.
==================  =======  ====================================================

For a plain square clock pulse the default intent is a pi transfer of the
addressed pair with ``delta_m`` equal to the beam sign (+1 up, -1 down) -
exactly the momentum bookkeeping of a resonant pi pulse. Clearouts remove all
ground-state population and carry no momentum fields.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Sequence

# ── Event kinds ───────────────────────────────────────────────────────────────
KIND_PULSE = 0
KIND_CLEAROUT = 1
KIND_CALLBACK = 2

# ── State effects ─────────────────────────────────────────────────────────────
EFFECT_FLIP = 0  # pi-like: the addressed pair's population swaps sides
EFFECT_SUPERPOSE = 1  # pi/2-like: both members of the addressed pair populated
EFFECT_NONE = 2  # internal states unchanged

# ── Addressed internal state ──────────────────────────────────────────────────
STATE_AUTO = -1  # resolve from the population walk
STATE_GROUND = 0
STATE_EXCITED = 1

# ── Momentum-class sentinel ───────────────────────────────────────────────────
#: "Resolve the addressed momentum class from the population walk". Far outside
#: any physical recoil count so it can never collide with a real value.
M_AUTO = -1048576


@dataclass(frozen=True)
class IntentEvent:
    """One decoded entry of the intent stream, with times in seconds.

    Times are in whatever frame the caller rebased them to (the trajectory
    predictor expects seconds since atom release).
    """

    t_start_s: float
    duration_s: float
    kind: int
    state_effect: int
    addressed_state: int
    addressed_m: int
    delta_m: int

    @property
    def t_centre_s(self) -> float:
        """Instantaneous-kick time: the centre of the event."""
        return self.t_start_s + self.duration_s / 2.0

    def __post_init__(self):
        if self.kind not in (KIND_PULSE, KIND_CLEAROUT, KIND_CALLBACK):
            raise ValueError(f"Unknown intent event kind {self.kind!r}")
        if self.state_effect not in (EFFECT_FLIP, EFFECT_SUPERPOSE, EFFECT_NONE):
            raise ValueError(f"Unknown intent state effect {self.state_effect!r}")
        if self.addressed_state not in (STATE_AUTO, STATE_GROUND, STATE_EXCITED):
            raise ValueError(f"Unknown addressed state {self.addressed_state!r}")


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
