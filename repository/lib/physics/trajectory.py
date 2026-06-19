"""
Intent-driven trajectory predictor
==================================

Pure host-side (no ARTIQ) prediction of where the atom clouds appear on the
camera sensor, computed from the **recorded intent stream** (see
:mod:`repository.lib.pulse_intent`) rather than from any physical model of the
pulses: every event is assumed to do exactly what it declared, 100 %
efficiently. This is deliberate - the full Bordé-frame simulation
(LMT_sim_scratch) stays a desk-side sanity check and is never in the
experiment's path, where a branch explosion would be undebuggable.

Model
-----

A single atom starts at the cloud centre, at rest, in the ground state, at the
moment of release (t = 0). The walker tracks a small set of population
*branches* ``(internal_state, m)`` - exactly the bookkeeping of
:func:`repository.lib.lmt_sequence.compile_sequence` - plus, for each branch,
its accumulated recoil displacement. Velocities are ``m * v_recoil`` along the
clock-beam (up) direction; momentum changes are applied instantaneously at the
**centre** of each event.

Gravity is common to every branch and added as the lab-frame parabola
``½ g t²`` at projection time; branch positions are tracked in the freely
falling frame.

Per intent event:

- pi transfer (``EFFECT_FLIP``): the addressed pair swaps sides; the branch
  gains ``+delta_m`` recoils going ground->excited (``-delta_m`` coming back).
- split (``EFFECT_SUPERPOSE``): both members of the addressed pair are
  populated; the new branch inherits the kick history.
- clearout: branches in the addressed internal state are removed.
- callback: the declared ``delta_m``/``state_effect`` applied to every branch
  (matching the declarative language's ``Callback`` semantics).

At an imaging time, the *ground port* is the set of ground-state branches and
the *excited port* the rest. A port with more than one branch (e.g. an open
interferometer) is reported at the unweighted mean of its branches with its
multiplicity flagged - never silently. An empty port (after a pi-intent
sequence the walker carries no lagging branch) is reported at the *other*
port's position with multiplicity 0 - the only real cloud is the best place
to point an ROI - or on the plain free-fall trajectory if both are empty.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Sequence

import numpy as np

from repository.lib.physics.ballistic import BallisticConfig
from repository.lib.physics.ballistic import recoil_velocity
from repository.lib.pulse_intent import AddressedState
from repository.lib.pulse_intent import IntentEvent
from repository.lib.pulse_intent import Kind
from repository.lib.pulse_intent import StateEffect

logger = logging.getLogger(__name__)


@dataclass(eq=False)  # identity comparison only; ndarray field breaks value eq
class _Branch:
    """One population branch in the freely-falling frame."""

    is_ground: bool
    m: int  # recoil quanta along the clock up direction
    displacement_m: np.ndarray  # accumulated recoil displacement at t_last_s
    t_last_s: float

    def advanced(self, t_s: float, v_r: float, direction: np.ndarray) -> "_Branch":
        """Ballistically advance this branch's displacement to time ``t_s``."""
        if t_s < self.t_last_s:
            raise ValueError(
                f"Intent events must be time-ordered: tried to advance a branch "
                f"from t={self.t_last_s} s back to t={t_s} s"
            )
        return _Branch(
            is_ground=self.is_ground,
            m=self.m,
            displacement_m=self.displacement_m
            + self.m * v_r * direction * (t_s - self.t_last_s),
            t_last_s=t_s,
        )


@dataclass(frozen=True)
class PortPrediction:
    """Predicted sensor position of one detection port at one imaging time."""

    x_pixel: float
    y_pixel: float
    multiplicity: int  # number of branches in this port (0 = empty port)


def walk_intent_events(
    events: Sequence[IntentEvent],
    up_to_t_s: float,
    cfg: BallisticConfig,
    initial_is_ground: bool = True,
    initial_m: int = 0,
) -> list[_Branch]:
    """Walk the intent stream up to ``up_to_t_s`` and return the branches.

    Only events whose centre falls at or before ``up_to_t_s`` are applied.
    Branch displacements are advanced to ``up_to_t_s`` before returning.
    """
    v_r = recoil_velocity(cfg)
    direction = cfg.clock_beam_direction

    branches = [
        _Branch(
            is_ground=initial_is_ground,
            m=initial_m,
            displacement_m=np.zeros(3),
            t_last_s=0.0,
        )
    ]

    for event in events:
        t_c = event.t_centre_s
        if t_c > up_to_t_s:
            break

        if event.kind == Kind.PULSE:
            branches = _apply_pulse(branches, event, t_c, v_r, direction)
        elif event.kind == Kind.CLEAROUT:
            branches = _apply_clearout(branches, event)
        elif event.kind == Kind.CALLBACK:
            branches = _apply_callback(branches, event, t_c, v_r, direction)
        else:  # pragma: no cover - IntentEvent already validates
            raise ValueError(f"Unknown intent event kind {event.kind!r}")

    return [b.advanced(up_to_t_s, v_r, direction) for b in branches]


def _transferred(
    branch: _Branch, event: IntentEvent, t_c: float, v_r: float, direction: np.ndarray
) -> _Branch:
    """The branch after a full transfer across the addressed pair."""
    advanced = branch.advanced(t_c, v_r, direction)
    delta = event.delta_m if branch.is_ground else -event.delta_m
    return _Branch(
        is_ground=not advanced.is_ground,
        m=advanced.m + delta,
        displacement_m=advanced.displacement_m,
        t_last_s=advanced.t_last_s,
    )


def _apply_pulse(
    branches: list[_Branch],
    event: IntentEvent,
    t_c: float,
    v_r: float,
    direction: np.ndarray,
) -> list[_Branch]:
    # Compare by identity: _Branch carries an ndarray, so value equality is
    # both meaningless here and unsafe in `in` checks.
    addressed_ids = {id(b) for b in branches if event.addresses_pair(b.is_ground, b.m)}
    if not addressed_ids and event.state_effect != StateEffect.NONE:
        logger.warning(
            "Intent pulse at t=%.6f s addresses (state=%s, m=%s) but no "
            "populated branch matches - skipping it",
            t_c,
            event.addressed_state,
            event.addressed_m,
        )
        return branches

    out: list[_Branch] = []
    for branch in branches:
        if id(branch) not in addressed_ids or event.state_effect == StateEffect.NONE:
            out.append(branch)
            continue
        if event.state_effect == StateEffect.FLIP:
            out.append(_transferred(branch, event, t_c, v_r, direction))
        else:  # EFFECT_SUPERPOSE: both members of the pair populated
            out.append(branch.advanced(t_c, v_r, direction))
            out.append(_transferred(branch, event, t_c, v_r, direction))
    return out


def _apply_clearout(branches: list[_Branch], event: IntentEvent) -> list[_Branch]:
    clear_ground = event.addressed_state != AddressedState.EXCITED
    survivors = [b for b in branches if b.is_ground != clear_ground]
    if not survivors:
        logger.warning(
            "Intent clearout at t=%.6f s removed every populated branch",
            event.t_start_s,
        )
    return survivors


def _apply_callback(
    branches: list[_Branch],
    event: IntentEvent,
    t_c: float,
    v_r: float,
    direction: np.ndarray,
) -> list[_Branch]:
    """Apply a declared callback effect to every branch.

    Mirrors :func:`repository.lib.lmt_sequence._apply_callback`: ``delta_m``
    is added to every branch as declared (no ground/excited sign flip).
    """
    out: list[_Branch] = []
    for branch in branches:
        advanced = branch.advanced(t_c, v_r, direction)
        m_new = advanced.m + event.delta_m
        if event.state_effect == StateEffect.NONE:
            out.append(_Branch(advanced.is_ground, m_new, advanced.displacement_m, t_c))
        elif event.state_effect == StateEffect.FLIP:
            out.append(
                _Branch(not advanced.is_ground, m_new, advanced.displacement_m, t_c)
            )
        else:  # EFFECT_SUPERPOSE
            out.append(_Branch(True, m_new, advanced.displacement_m, t_c))
            out.append(_Branch(False, m_new, advanced.displacement_m, t_c))
    return out


def _port_position_lab(
    port_branches: list[_Branch], t_image_s: float, cfg: BallisticConfig
) -> tuple[np.ndarray, int]:
    """Lab-frame position of one port at the imaging time.

    Empty port -> the plain free-fall trajectory (multiplicity 0).
    """
    gravity_term = 0.5 * cfg.gravity_vec_m_per_s2 * t_image_s * t_image_s
    if not port_branches:
        return gravity_term, 0
    mean_displacement = np.mean([b.displacement_m for b in port_branches], axis=0)
    return mean_displacement + gravity_term, len(port_branches)


def predict_port_positions_lab(
    events: Sequence[IntentEvent],
    t_image_s: float,
    cfg: BallisticConfig,
    initial_is_ground: bool = True,
    initial_m: int = 0,
) -> dict[str, tuple[np.ndarray, int]]:
    """Lab-frame 3D positions of the ground and excited ports at ``t_image_s``.

    Returns ``{"ground": (pos_lab_m, multiplicity), "excited": ...}``.
    """
    branches = walk_intent_events(
        events,
        up_to_t_s=t_image_s,
        cfg=cfg,
        initial_is_ground=initial_is_ground,
        initial_m=initial_m,
    )
    ground = [b for b in branches if b.is_ground]
    excited = [b for b in branches if not b.is_ground]
    return {
        "ground": _port_position_lab(ground, t_image_s, cfg),
        "excited": _port_position_lab(excited, t_image_s, cfg),
    }


def predict_port_pixels(
    events: Sequence[IntentEvent],
    t_image_ground_s: float,
    t_image_excited_s: float,
    cfg: BallisticConfig,
    initial_is_ground: bool = True,
    initial_m: int = 0,
) -> dict[str, PortPrediction]:
    """Predict the sensor pixel position of each detection port.

    The ground port is evaluated at ``t_image_ground_s`` (first fast-kinetics
    shot) and the excited port at ``t_image_excited_s`` (second shot). An
    empty intent stream gives plain free fall for both ports.

    A port holding more than one branch (open interferometer) is centred on
    the unweighted branch mean with ``multiplicity > 1`` so callers can flag
    it. An empty port takes the other port's position (the only real cloud)
    with ``multiplicity = 0``; if both are empty, plain free fall.
    """
    results: dict[str, PortPrediction] = {}
    for port, other, t_image_s in (
        ("ground", "excited", t_image_ground_s),
        ("excited", "ground", t_image_excited_s),
    ):
        positions = predict_port_positions_lab(
            events,
            t_image_s=t_image_s,
            cfg=cfg,
            initial_is_ground=initial_is_ground,
            initial_m=initial_m,
        )
        pos_lab, multiplicity = positions[port]
        if multiplicity == 0 and positions[other][1] > 0:
            pos_lab = positions[other][0]
        x_pix, y_pix = cfg.camera.project(pos_lab)
        results[port] = PortPrediction(
            x_pixel=x_pix, y_pixel=y_pix, multiplicity=multiplicity
        )
    return results


def rebase_record_times_mu(
    times_mu: Sequence[int],
    t_playback_start_mu: int,
    t_release_mu: int,
    ref_period_s: float,
) -> np.ndarray:
    """Convert DMA-recording-relative timestamps to seconds since release.

    ``core_dma.record()`` resets the timeline cursor to zero, so timestamps
    captured inside a recording are relative to the recording start. During
    playback the recorded events run at ``t_playback_start_mu + t_recorded``,
    which this rebases against the (live-timeline) release timestamp:

        t_s = (t_playback_start_mu + t_mu - t_release_mu) * ref_period_s
    """
    times = np.asarray(times_mu, dtype=np.int64)
    return (
        times + np.int64(t_playback_start_mu) - np.int64(t_release_mu)
    ) * ref_period_s


def live_times_to_seconds_since_release(
    times_mu: Sequence[int],
    t_release_mu: int,
    ref_period_s: float,
) -> np.ndarray:
    """Convert live-timeline timestamps to seconds since release."""
    times = np.asarray(times_mu, dtype=np.int64)
    return (times - np.int64(t_release_mu)) * ref_period_s
