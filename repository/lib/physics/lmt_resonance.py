"""
LMT pulse resonance predictor
=============================

Pure host-side (no ARTIQ) physics for predicting the resonance of large
momentum transfer (LMT) clock pulses on the 698 nm transition.

This is a minimal port of the Bordé-frame resonance bookkeeping from the
``lmt_sim`` simulation package (https://github.com/charlesbaynham/LMT_sim_scratch),
restricted to the single question the experiment needs answered at build time:

    "Which OPLL offset frequency addresses momentum class m with the up or
    down beam?"

Conventions
-----------

- Momentum classes ``m`` are integer multiples of the single-photon recoil
  ``hbar * k``, counted **positive in the launch (upward) direction**.
- Internal states are labelled ``"g"`` (ground) and ``"e"`` (excited).
- Beam directions are described by ``beam_sign``: ``+1`` for the up beam and
  ``-1`` for the down beam.
- A beam with sign ``s`` couples the pair ``|g, m_g> <-> |e, m_g + s>``.

The atomic-frame resonance detuning (relative to the unperturbed transition,
for an atom at rest) of the pair with ground class ``m_g`` driven by beam
``s`` is

    delta_atom = s * m_g * kick + kick / 2

where ``kick = 2 * f_recoil`` is the Doppler shift produced by one photon
recoil (~9.4 kHz for Sr-87 at 698 nm) and the constant ``kick / 2`` is the
photon-recoil energy term. Both terms are always included - there are no
back-compatibility switches.

OPLL mapping
------------

Both the up and down beams are derived from the same laser, whose frequency
is steered by the OPLL offset DDS. An increase of the OPLL offset shifts the
*atomic detuning* of every transition by the same amount with a fixed
hardware sign. The sign convention used throughout the declarative LMT stack
(matching the empirically-verified frequencies in the legacy LMT code) is

    f_opll = START_OPLL + s * D(t) - opll_m_term_hz(...) + user_offset

where ``D(t)`` is the gravity Doppler accumulated since release (computed at
runtime in the kernel from the pulse timestamp) and ``opll_m_term_hz`` is the
static, m-dependent part computed here on the host.

Relative to the legacy loop formulas (which omit the recoil energy term),
``f_opll`` differs by exactly ``-s * kick / 2``; this is pinned by the unit
tests in ``tests/test_lmt_resonance.py``.
"""

from dataclasses import dataclass
from enum import IntEnum
from typing import Sequence

import scipy.constants

from repository.lib import constants

GROUND = "g"
EXCITED = "e"

#: Photon recoil energy of the 698 nm clock transition expressed as a
#: frequency: f_rec = hbar * k^2 / (4 * pi * M) = h / (2 * M * lambda^2).
RECOIL_FREQUENCY_HZ = scipy.constants.h / (
    2 * constants.SR_ATOM_MASS_KG * constants.CLOCK_WAVELENGTH_M**2
)

#: Doppler shift produced by a single photon recoil: v_rec / lambda. This is
#: the frequency step between adjacent momentum classes and equals twice the
#: recoil frequency. The empirically-used value in the experiment is
#: ``constants.MOMENTUM_KICK_DETUNING`` (9.4 kHz); the two agree to < 0.1 %.
DOPPLER_PER_KICK_HZ = 2 * RECOIL_FREQUENCY_HZ


def transition_detuning_hz(
    m_ground: int,
    k_sign: int,
    kick_hz: float = constants.MOMENTUM_KICK_DETUNING,
) -> float:
    """Atomic-frame resonance detuning of the pair with ground class ``m_ground``.

    The beam with sign ``k_sign`` couples ``|g, m_ground> <-> |e, m_ground + k_sign>``
    at a detuning (for an atom at rest) of

        delta = k_sign * m_ground * kick + kick / 2

    Args:
        m_ground: Momentum class of the ground state of the addressed pair.
        k_sign: Beam direction, +1 (up) or -1 (down).
        kick_hz: Doppler shift per photon recoil. Defaults to the
            empirically-calibrated ``constants.MOMENTUM_KICK_DETUNING``.

    Returns:
        Detuning in Hz.
    """
    if k_sign not in (1, -1):
        raise ValueError(f"k_sign must be +1 or -1, got {k_sign!r}")
    return k_sign * m_ground * kick_hz + kick_hz / 2.0


def addressed_ground_class(
    effective_detuning_hz: float,
    k_sign: int,
    kick_hz: float = constants.MOMENTUM_KICK_DETUNING,
) -> float:
    """Inverse of :func:`transition_detuning_hz` (port of ``lmt_sim``).

    Returns the (generally non-integer) ground-state momentum class that a
    pulse at the given atomic-frame detuning addresses:

        m_ground = (delta - kick / 2) / (k_sign * kick)

    Args:
        effective_detuning_hz: Atomic-frame detuning of the pulse in Hz.
        k_sign: Beam direction, +1 (up) or -1 (down).
        kick_hz: Doppler shift per photon recoil.

    Returns:
        Addressed ground-state momentum class (float).
    """
    if k_sign not in (1, -1):
        raise ValueError(f"k_sign must be +1 or -1, got {k_sign!r}")
    return (effective_detuning_hz - kick_hz / 2.0) / (k_sign * kick_hz)


def pair_ground_class(m: int, internal_state: str, beam_sign: int) -> int:
    """Ground class of the pair addressed when driving state ``(internal_state, m)``.

    A beam with sign ``s`` couples ``|g, m_g> <-> |e, m_g + s>``, so driving a
    populated ground state gives ``m_g = m`` while driving a populated excited
    state gives ``m_g = m - s``.

    Args:
        m: Momentum class of the populated state being addressed.
        internal_state: ``"g"`` or ``"e"``.
        beam_sign: Beam direction, +1 (up) or -1 (down).

    Returns:
        Ground-state momentum class of the addressed pair.
    """
    if beam_sign not in (1, -1):
        raise ValueError(f"beam_sign must be +1 or -1, got {beam_sign!r}")
    if internal_state == GROUND:
        return m
    if internal_state == EXCITED:
        return m - beam_sign
    raise ValueError(f"internal_state must be 'g' or 'e', got {internal_state!r}")


def opll_m_term_hz(
    m: int,
    internal_state: str,
    beam_sign: int,
    kick_hz: float = constants.MOMENTUM_KICK_DETUNING,
) -> float:
    """Static m-dependent term of the OPLL frequency for an LMT pulse.

    This is the atomic-frame detuning of the addressed pair,
    :func:`transition_detuning_hz`, to be used in the kernel formula

        f_opll = START_OPLL + beam_sign * D(t) - opll_m_term_hz(...) + offset

    where ``D(t)`` is the runtime gravity Doppler term.

    Args:
        m: Momentum class of the populated state being addressed.
        internal_state: Internal state (``"g"`` or ``"e"``) of that population.
        beam_sign: Beam direction, +1 (up) or -1 (down).
        kick_hz: Doppler shift per photon recoil.

    Returns:
        Frequency term in Hz.
    """
    m_g = pair_ground_class(m, internal_state, beam_sign)
    return transition_detuning_hz(m_g, beam_sign, kick_hz=kick_hz)


# ── Recorded-intent vocabulary ────────────────────────────────────────────────
#
# The declarative-LMT pulse recorder archives, alongside the pulse facts, an
# *intent stream*: one row per atom-affecting event describing what it is meant
# to do to the populations. The host-side spacetime-trajectory reconstruction
# (:mod:`repository.lib.physics.lmt_spacetime`, drawn by the trajectory applet)
# walks that stream exactly. The integer codes and the decode below are the
# shared schema for the broadcast ``pulse_intent_record`` dataset.


def _ground_class_of_pair(m: int, is_ground: bool, beam_sign: int) -> int:
    """Ground class ``m_g`` of the pair ``|g, m_g> <-> |e, m_g + beam_sign>``.

    A beam with sign ``s`` couples ``|g, m_g> <-> |e, m_g + s>``, so the
    populated state ``(is_ground, m)`` lies on the ground side at ``m_g = m`` or
    on the excited side at ``m_g = m - s``. This is the pairing rule shared with
    :meth:`IntentEvent.addresses_pair`.
    """
    return m if is_ground else m - beam_sign


class Kind(IntEnum):
    PULSE = 0
    CLEAROUT = 1
    # No longer emitted: callbacks self-describe as PULSE rows (one ordinary
    # pulse intent row per declared callback action). Kept to document the
    # record schema and preserve the IntEnum numbering.
    CALLBACK = 2


class StateEffect(IntEnum):
    FLIP = 0  # pi-like: the addressed pair's population swaps sides
    SUPERPOSE = 1  # pi/2-like: both members of the addressed pair populated
    NONE = 2  # internal states unchanged


class AddressedState(IntEnum):
    AUTO = -1  # resolve from the population walk
    GROUND = 0
    EXCITED = 1


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

        ``AddressedState.AUTO``/``M_AUTO`` address every populated branch through
        the pulse's own coupling - correct for single-chain sequences. An
        explicitly declared pair ``|g, m_g> <-> |e, m_g + delta_m>`` addresses
        only its two members, leaving e.g. a parked interferometer arm
        untouched.
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
        # and population on either side of the pair participates. The pairing
        # rule is the shared one used at compile time (delta_m plays beam_sign).
        m_g = _ground_class_of_pair(
            self.addressed_m,
            self.addressed_state == AddressedState.GROUND,
            self.delta_m,
        )
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
) -> "list[IntentEvent]":
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
