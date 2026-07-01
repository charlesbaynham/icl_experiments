"""
Intent-driven LMT spacetime diagram
====================================

Host-side reconstruction of the atom-cloud spacetime trajectory of the most
recent recorded LMT sequence, drawn the same way the ``lmt_sim`` desk-side
simulator draws it: a two-panel space-time / momentum diagram.

Unlike the simulator -- which only has the *pulse facts* (frequencies and
durations) and must infer flip/drift/split from a Bordé Rabi-probability
heuristic -- the declarative-LMT stack records the **intent stream** alongside
the facts (see :mod:`repository.lib.physics.lmt_resonance`). Every atom-affecting event
self-describes what it is meant to do to the populations, assumed 100 %
efficient. So here the trajectory is walked *exactly* from the recorded intent,
with no Rabi guesswork: the branch bookkeeping is identical to the dynamic-ROI
predictor in :mod:`repository.lib.physics.trajectory`, just extended to keep the
full per-event history each branch needs to be plotted.

The momentum frame is the freely-falling frame (gravity is common to every
branch and would only obscure the arm separation), exactly as the simulator's
spacetime diagram. ``z`` is the recoil displacement along the clock (up) beam in
metres; ``m`` is the momentum in integer photon recoils; ``v_z = m * v_recoil``.

This module is pure host code (no ARTIQ); the drawing lives in
``repository.lib.applets.lmt_trajectory_applet``.
"""

import logging
from dataclasses import dataclass

import numpy as np
import scipy.constants as _const

from repository.lib import constants
from repository.lib.physics import lmt_resonance
from repository.lib.physics.lmt_resonance import AddressedState
from repository.lib.physics.lmt_resonance import Kind
from repository.lib.physics.lmt_resonance import StateEffect

logger = logging.getLogger(__name__)

# --- Physical constants -----------------------------------------------------

#: Single-photon recoil speed ``v_r = h / (m λ)`` (~6.6 mm/s for Sr-87), from
#: the single source of truth in ``repository.lib.constants`` so this tracks the
#: configured isotope and clock transition.
RECOIL_VELOCITY = _const.h / (constants.SR_ATOM_MASS_KG * constants.CLOCK_WAVELENGTH_M)

#: Sentinels written by ``PulseDMARecording`` as length-1 records. Stored as
#: float64 and so compared with a tolerance, not for exact equality.
INTENT_RECORD_SAME_AS_LAST_SENTINEL = -1.0
INTENT_RECORD_DISABLED_SENTINEL = -2.0
_INTENT_RECORD_SENTINEL_TOL = 0.5


# --- Drawing-sequence event types -------------------------------------------
#
# The walk reconstructs a contiguous timeline of drawing events whose durations
# sum to the real sequence time, so ``build_plot_trace`` can rebuild positions
# from momentum. Only ``Pulse`` is a momentum kick (drawn with a mid-point
# kink); ``Drift`` (free evolution between events) and ``Clearout`` are plain
# ballistic segments. The classes intentionally mirror ``lmt_sim``'s so the
# drawing code reads the same.


@dataclass(frozen=True)
class Pulse:
    """One atom-affecting kick (clock pulse or callback) on the drawing timeline.

    ``k`` is the beam sign used only for the shading colour (+1 up / blue,
    -1 down / red), taken from the sign of the intent ``delta_m``. ``m_low`` /
    ``m_high`` bound the momentum classes the pulse actually addressed (for the
    overlaid band); ``None`` when the pulse addressed no populated branch.
    """

    k: int
    duration: float
    label: str = "pulse"
    m_low: float | None = None
    m_high: float | None = None


@dataclass(frozen=True)
class Drift:
    duration: float
    label: str = "drift"


@dataclass(frozen=True)
class Clearout:
    duration: float
    label: str = "clearout"


# --- One branch of the wavefunction (per-event history) ---------------------


@dataclass(eq=False)  # identity comparison only; list/ndarray fields break value eq
class Cloud:
    """One population branch, with per-event histories aligned to the sequence.

    ``times``/``z``/``m``/``is_ground`` grow by one entry per drawing event the
    branch lives through (entry 0 is release). ``alive`` is cleared when a
    clearout removes the branch; ``fork_index`` records the sequence index where
    a split branch forked off its parent and ``color_index`` keys its colour.
    """

    times: list
    z: list
    m: list
    is_ground: list
    labels: list
    alive: bool = True
    fork_index: int = 0
    color_index: int = 0

    @property
    def v(self):
        return self.m[-1] * RECOIL_VELOCITY

    def _fork(self):
        return Cloud(
            times=list(self.times),
            z=list(self.z),
            m=list(self.m),
            is_ground=list(self.is_ground),
            labels=list(self.labels),
            fork_index=self.fork_index,
            color_index=self.color_index,
        )


# --- Walk the intent stream into a drawing sequence + cloud histories --------


def _append_drift(cloud: Cloud, t: float, dt: float, label: str):
    cloud.times.append(t)
    cloud.z.append(cloud.z[-1] + cloud.v * dt)
    cloud.m.append(cloud.m[-1])
    cloud.is_ground.append(cloud.is_ground[-1])
    cloud.labels.append(label)


def _append_transfer(cloud: Cloud, t: float, dt: float, delta_m: int, label: str):
    """Append a full state transfer (pi-like): swap internal state, kick m."""
    dm = delta_m if cloud.is_ground[-1] else -delta_m
    new_m = cloud.m[-1] + dm
    cloud.times.append(t)
    cloud.z.append(cloud.z[-1] + new_m * RECOIL_VELOCITY * dt)
    cloud.m.append(new_m)
    cloud.is_ground.append(not cloud.is_ground[-1])
    cloud.labels.append(label)


def _append_kick(cloud: Cloud, t: float, dt: float, delta_m: int, label: str):
    """Append a pure momentum kick (NONE: internal state unchanged)."""
    new_m = cloud.m[-1] + delta_m
    cloud.times.append(t)
    cloud.z.append(cloud.z[-1] + new_m * RECOIL_VELOCITY * dt)
    cloud.m.append(new_m)
    cloud.is_ground.append(cloud.is_ground[-1])
    cloud.labels.append(label)


def walk_intent_to_trajectory(events):
    """Walk an intent stream into ``(sequence, clouds, clearout_times)``.

    ``events`` is a list of :class:`~repository.lib.physics.lmt_resonance.IntentEvent` in
    firing order. Returns the contiguous drawing ``sequence`` (list of
    :class:`Pulse`/:class:`Drift`/:class:`Clearout`), the list of
    :class:`Cloud` branches, and an array of clearout times (seconds). Times are
    rebased so the first event starts at ``t = 0``.

    The branch semantics are exactly those of the recorded intent (and of
    :mod:`repository.lib.physics.trajectory`): a flip transfers the addressed
    pair, a superpose splits it, a clearout removes the addressed internal
    state, and a wait is a pure dark time drawn as free-evolution drift.
    Callbacks carry no special record kind - each callback action is an
    ordinary ``Kind.PULSE`` row and flows through the pulse path here.
    """
    events = sorted(events, key=lambda e: e.t_centre_s)
    if not events:
        return [], [], np.asarray([])

    t0 = events[0].t_start_s

    sequence: list = []
    clearout_times: list = []
    clouds = [Cloud(times=[0.0], z=[0.0], m=[0], is_ground=[True], labels=["release"])]
    next_color_index = 1
    t_cursor = 0.0  # seconds since the first event start

    def drift_all(dt: float, label: str):
        nonlocal t_cursor
        t_cursor += dt
        for cloud in clouds:
            if cloud.alive:
                _append_drift(cloud, t_cursor, dt, label)

    for event in events:
        t_start = event.t_start_s - t0
        dt = event.duration_s

        # Fill the gap since the previous event with a free-evolution drift.
        gap = t_start - t_cursor
        if gap > 1e-12:
            sequence.append(Drift(duration=gap))
            drift_all(gap, "drift")

        if event.kind == Kind.WAIT:
            # Pure dark time: draw its duration as free-evolution drift, leaving
            # every branch's internal state and momentum untouched.
            sequence.append(Drift(duration=dt))
            drift_all(dt, "drift")
            continue

        if event.kind == Kind.CLEAROUT:
            sequence.append(Clearout(duration=dt))
            drift_all(dt, "clearout")
            clearout_times.append(t_cursor)
            clear_ground = event.addressed_state != AddressedState.EXCITED
            for cloud in clouds:
                if cloud.alive and cloud.is_ground[-1] == clear_ground:
                    cloud.alive = False
            continue

        # KIND_PULSE: an atom-affecting kick drawn as a Pulse.
        t_cursor += dt
        k = -1 if event.delta_m < 0 else +1

        # A NONE pulse is a pure momentum kick on the single declared
        # population (the pure-kick callback action); FLIP/SUPERPOSE act on the
        # whole addressed pair.
        if event.state_effect == StateEffect.NONE:
            clear_excited = event.addressed_state == AddressedState.EXCITED
            addressed = [
                c
                for c in clouds
                if c.alive
                and c.is_ground[-1] == (not clear_excited)
                and c.m[-1] == event.addressed_m
            ]
        else:
            addressed = [
                c
                for c in clouds
                if c.alive and event.addresses_pair(c.is_ground[-1], c.m[-1])
            ]
        if not addressed and event.state_effect != StateEffect.NONE:
            logger.warning(
                "Intent pulse at t=%.6f s addresses (state=%s, m=%s) but no live "
                "branch matches - drawing it as a no-op",
                t_cursor,
                event.addressed_state,
                event.addressed_m,
            )

        m_involved: list = []
        new_clouds: list = []
        for cloud in clouds:
            if not cloud.alive or cloud not in addressed:
                if cloud.alive:
                    _append_drift(cloud, t_cursor, dt, "pulse")
                new_clouds.append(cloud)
                continue

            m_involved.append(cloud.m[-1])
            if event.state_effect == StateEffect.FLIP:
                _append_transfer(cloud, t_cursor, dt, event.delta_m, "pulse")
                m_involved.append(cloud.m[-1])
                new_clouds.append(cloud)
            elif event.state_effect == StateEffect.SUPERPOSE:
                drifter = cloud._fork()
                flipper = cloud._fork()
                flipper.fork_index = len(cloud.times)
                flipper.color_index = next_color_index
                next_color_index += 1
                _append_drift(drifter, t_cursor, dt, "pulse")
                _append_transfer(flipper, t_cursor, dt, event.delta_m, "pulse")
                m_involved.append(flipper.m[-1])
                new_clouds.extend([drifter, flipper])
            else:  # StateEffect.NONE: pure momentum kick, internal state unchanged
                _append_kick(cloud, t_cursor, dt, event.delta_m, "pulse")
                m_involved.append(cloud.m[-1])
                new_clouds.append(cloud)
        clouds = new_clouds

        band = (min(m_involved), max(m_involved)) if m_involved else (None, None)
        sequence.append(
            Pulse(k=k, duration=dt, label="pulse", m_low=band[0], m_high=band[1])
        )

    return sequence, clouds, np.asarray(clearout_times)


# --- Drawing trace (identical convention to lmt_sim / lmt_trajectory) --------


def build_plot_trace(sequence, cloud):
    """Build the midpoint-convention drawing trace for one cloud.

    A pulse is drawn as two z-segments (drift to the pulse centre, then drift
    out at the new momentum) and the momentum as a vertical step at the pulse
    centre. The trace is sliced to start one event before the cloud's fork so
    split branches only appear from their split point.

    Returns ``(times, positions, m_times, m, ground, m_ground)`` as arrays, all
    in SI units (seconds, metres, integer recoils).
    """
    times = [cloud.times[0]]
    positions = [cloud.z[0]]
    momentum_times = [cloud.times[0]]
    momentum = [cloud.m[0]]
    ground = [cloud.is_ground[0]]
    m_ground = [cloud.is_ground[0]]

    current_time = cloud.times[0]
    current_position = cloud.z[0]
    current_m = cloud.m[0]
    current_ground = cloud.is_ground[0]

    for i in range(len(cloud.times) - 1):
        event = sequence[i]
        dt = event.duration
        event_end_time = current_time + dt

        if isinstance(event, Pulse):
            mid_time = current_time + dt / 2
            mid_position = current_position + current_m * RECOIL_VELOCITY * dt / 2
            next_m = cloud.m[i + 1]
            next_ground = cloud.is_ground[i + 1]
            end_position = mid_position + next_m * RECOIL_VELOCITY * dt / 2

            times.extend([mid_time, event_end_time])
            positions.extend([mid_position, end_position])
            momentum_times.extend([mid_time, mid_time, event_end_time])
            momentum.extend([current_m, next_m, next_m])
            ground.extend([current_ground, next_ground])
            m_ground.extend([current_ground, next_ground, next_ground])
        else:
            next_m = cloud.m[i + 1]
            next_ground = cloud.is_ground[i + 1]
            end_position = current_position + current_m * RECOIL_VELOCITY * dt

            times.append(event_end_time)
            positions.append(end_position)
            momentum_times.append(event_end_time)
            momentum.append(next_m)
            ground.append(next_ground)
            m_ground.append(next_ground)

        current_time = event_end_time
        current_position = positions[-1]
        current_m = momentum[-1]
        current_ground = ground[-1]

    fi = max(0, cloud.fork_index - 1)
    z_start = sum(2 if isinstance(sequence[i], Pulse) else 1 for i in range(fi))
    m_start = sum(3 if isinstance(sequence[i], Pulse) else 1 for i in range(fi))

    return (
        np.asarray(times[z_start:]),
        np.asarray(positions[z_start:]),
        np.asarray(momentum_times[m_start:]),
        np.asarray(momentum[m_start:]),
        np.asarray(ground[z_start:], dtype=bool),
        np.asarray(m_ground[m_start:], dtype=bool),
    )


# --- Decode the broadcast ``pulse_intent_record`` dataset -------------------


def _is_sentinel(record, sentinel):
    return (
        len(record) == 1
        and len(record[0]) == 1
        and abs(float(record[0][0]) - sentinel) < _INTENT_RECORD_SENTINEL_TOL
    )


def most_recent_valid_record(records):
    """Return the most recently *stored* 7-row record from ``pulse_intent_record``.

    ``records`` is the live broadcast dataset: a list whose entries are either a
    genuine record (7 rows of ``num_events`` floats: kinds, start times,
    durations, state effects, addressed states, addressed m, delta m) or a
    length-1 sentinel (``[[-1.0]]`` "same as last", ``[[-2.0]]`` "disabled").

    Scanning from the end, the first genuine record is returned -- a trailing
    "same as last" sentinel just re-uses it, and "disabled" shots stored
    nothing. Returns ``None`` if no genuine record exists yet.
    """
    for record in reversed(list(records)):
        if len(record) == 7 and not _is_sentinel(
            record, INTENT_RECORD_SAME_AS_LAST_SENTINEL
        ):
            return [np.asarray(row, dtype=float) for row in record]
    return None


def intent_events_from_record(record):
    """Build :class:`IntentEvent` list from one decoded 7-row intent record.

    Row order matches ``PulseDMARecording._save_intent_record_to_dataset``:
    ``[kinds, start_times_s, durations_s, state_effects, addressed_states,
    addressed_m, delta_m]``.
    """
    kinds, start_s, dur_s, effects, states, addr_m, delta_m = record
    return lmt_resonance.intent_events_from_arrays(
        t_start_s=start_s,
        duration_s=dur_s,
        kinds=[int(round(x)) for x in kinds],
        state_effects=[int(round(x)) for x in effects],
        addressed_states=[int(round(x)) for x in states],
        addressed_m=[int(round(x)) for x in addr_m],
        delta_m=[int(round(x)) for x in delta_m],
    )


def infer_trajectory_from_intent_record(records):
    """End-to-end: decode the most recent valid intent record and walk it.

    Returns ``(sequence, clouds, clearout_times)``, or ``None`` if no valid
    sequence has been recorded yet (or the record holds no events).
    """
    record = most_recent_valid_record(records)
    if record is None:
        return None
    if len(record[0]) == 0:
        return None
    events = intent_events_from_record(record)
    return walk_intent_to_trajectory(events)


#: matplotlib tab10 palette as RGB tuples, so the applet's colours match the
#: simulator's matplotlib figure exactly.
TAB10_RGB = [
    (31, 119, 180),
    (255, 127, 14),
    (44, 160, 44),
    (214, 39, 40),
    (148, 103, 189),
    (140, 86, 75),
    (227, 119, 194),
    (127, 127, 127),
    (188, 189, 34),
    (23, 190, 207),
]
