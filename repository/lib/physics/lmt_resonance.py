"""
LMT pulse resonance predictor and recorded-intent vocabulary
============================================================

Pure host-side (no ARTIQ) physics for predicting the resonance of large momentum
transfer (LMT) clock pulses on the 698 nm transition, plus the shared vocabulary
of the recorded *intent* stream.

This module has two responsibilities:

1. **Resonance physics** - a minimal port of the Bordé-frame resonance
   bookkeeping from the ``lmt_sim`` simulation package
   (https://github.com/charlesbaynham/LMT_sim_scratch), restricted to the single
   question the experiment needs answered at build time:

       "Which OPLL offset frequency addresses momentum class m with the up or
       down beam?"

2. **Recorded-intent vocabulary** - the enums (:class:`Kind`,
   :class:`StateEffect`, :class:`AddressedState`), the :data:`M_AUTO` sentinel
   and the :class:`IntentEvent` decoding helpers that describe the *intent*
   stream recorded by
   :class:`~repository.lib.fragments.pulse_recorder_and_tracker.PulseDMARecording`
   alongside the pulse facts. Every atom-affecting event (clock pulses, 461 nm
   clearouts and "callback" pulses) registers one entry describing **what it is
   meant to do to the atomic populations, assumed 100 % efficient**. The stream
   is consumed by the dynamic-ROI trajectory predictor
   (:mod:`repository.lib.physics.trajectory`) and the spacetime diagram
   (:mod:`repository.lib.physics.lmt_spacetime`).

Conventions
-----------

- Momentum classes ``m`` are integer multiples of the single-photon recoil
  ``hbar * k``, counted **positive in the upward direction**.
- Internal states are :class:`InternalState` members ``GROUND`` and ``EXCITED``.
- Beam directions are described by ``beam_sign``: ``+1`` for the up beam and
  ``-1`` for the down beam.
- A beam with sign ``s`` couples the pair ``|g, m_g> <-> |e, m_g + s>``.

Intent record schema
---------------------

One entry per atom-affecting event, in firing order:

==================  =======  ====================================================
field               type     meaning
==================  =======  ====================================================
``t_start_mu``      int64    timeline position when the event starts
``duration_mu``     int64    event duration
``kind``            int32    ``Kind.PULSE`` or ``Kind.CLEAROUT``. (``Kind.CALLBACK``
                             is reserved but no longer emitted: a callback
                             records one ordinary ``Kind.PULSE`` row per
                             declared action.)
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
                             direction gets the negative).
==================  =======  ====================================================

The atomic-frame resonance detuning (relative to the unperturbed transition, for
an atom at rest) of the pair with ground class ``m_g`` driven by beam ``s`` is

    delta_atom = s * m_g * kick + kick / 2

where ``kick = 2 * f_recoil`` is the Doppler shift produced by one photon recoil
(~9.4 kHz for Sr-87 at 698 nm) and the constant ``kick / 2`` is the
photon-recoil energy term.

OPLL mapping
------------

Both the up and down beams are derived from the same laser, whose frequency is
steered by the OPLL offset DDS. The Sirah laser is locked to the *negative
sideband* of the beat with the ECDL. Positive changes to the OPLL reference
therefore result in negative changes to the frequency at the atoms. Since we
tune the other AOMs (particularly the SUServo delivery AOM) for resonance at the
velocity slice, the first pulse is always resonant at
`START_OPLL - constants.MOMENTUM_KICK_DETUNING/2`. The subsequent frequencies of
the OPLL should therefore be:

```
    f_opll = START_OPLL + s * D(t) - opll_m_term_hz(...) + user_offset
```

where ``D(t)`` is the gravity Doppler accumulated since release (computed at
runtime in the kernel from the pulse's timestamp and ramped throughout the
pulse) and ``opll_m_term_hz`` is the static, m-dependent part computed here on
the host, calculated for the pulse mid-point.
"""

from dataclasses import dataclass
from enum import Enum
from enum import IntEnum
from typing import Sequence

import scipy.constants

from repository.lib import constants


class InternalState(Enum):
    GROUND = "g"
    EXCITED = "e"


GROUND = InternalState.GROUND
EXCITED = InternalState.EXCITED

#: Photon recoil energy of the 698 nm clock transition expressed as a
#: frequency: f_rec = hbar * k^2 / (4 * pi * M) = h / (2 * M * lambda^2).
RECOIL_FREQUENCY_HZ = scipy.constants.h / (
    2 * constants.SR_ATOM_MASS_KG * constants.CLOCK_WAVELENGTH_M**2
)

#: Doppler shift produced by a single photon recoil: v_rec / lambda. This is
#: the frequency step between adjacent momentum classes and equals twice the
#: recoil frequency. ``constants.MOMENTUM_KICK_DETUNING`` is the same quantity
#: derived from fundamental constants, so the two are identical.
DOPPLER_PER_KICK_HZ = constants.MOMENTUM_KICK_DETUNING


def v0_doppler_term_hz(
    beam_sign: int,
    initial_velocity_m_s: float = constants.DEFAULT_INITIAL_VELOCITY_M_S,
    wavelength_m: float = constants.CLOCK_WAVELENGTH_M,
) -> float:
    """OPLL correction (Hz) for the atom's initial-velocity Doppler shift.

    ``beam_sign`` is +1 (up) or -1 (down); the correction is opposite-signed up
    versus down.
    """
    if beam_sign not in (1, -1):
        raise ValueError(f"beam_sign must be +1 or -1, got {beam_sign!r}")
    return -beam_sign * initial_velocity_m_s / wavelength_m


def probe_stark_term_hz(
    rabi_hz: float,
    alpha_hz_s2: float = constants.DEFAULT_PROBE_STARK_ALPHA_HZ_S2,
) -> float:
    """OPLL correction (Hz) for the probe AC-Stark light shift.

    The light shift raises the resonance by ``alpha * rabi**2``, so to stay
    resonant the OPLL centre is moved with it: the correction added to the OPLL
    frequency is ``-alpha * rabi**2``. (``alpha`` is our convention for the
    light shift per unit ``rabi**2``.)
    """
    return -alpha_hz_s2 * rabi_hz * rabi_hz


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
    # TODO: validate against LMT_simulations by running a no-atom sequence, extracting the reported pulse sequence and putting it through LMT_simulations to test it
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


def _ground_class_of_pair(m: int, is_ground: bool, beam_sign: int) -> int:
    """Ground class ``m_g`` of the pair ``|g, m_g> <-> |e, m_g + beam_sign>``.

    A beam with sign ``s`` couples ``|g, m_g> <-> |e, m_g + s>``, so the
    populated state ``(is_ground, m)`` lies on the ground side at ``m_g = m`` or
    on the excited side at ``m_g = m - s``. This is the single source of the
    pairing rule, shared by :func:`pair_ground_class` and
    :meth:`IntentEvent.addresses_pair`.
    """
    return m if is_ground else m - beam_sign


def pair_ground_class(m: int, internal_state: InternalState, beam_sign: int) -> int:
    """Ground class of the pair addressed when driving state ``(internal_state, m)``.

    A beam with sign ``s`` couples ``|g, m_g> <-> |e, m_g + s>``, so driving a
    populated ground state gives ``m_g = m`` while driving a populated excited
    state gives ``m_g = m - s``.

    Args:
        m: Momentum class of the populated state being addressed.
        internal_state: :data:`GROUND` or :data:`EXCITED`.
        beam_sign: Beam direction, +1 (up) or -1 (down).

    Returns:
        Ground-state momentum class of the addressed pair.
    """
    if beam_sign not in (1, -1):
        raise ValueError(f"beam_sign must be +1 or -1, got {beam_sign!r}")
    if internal_state == GROUND:
        return _ground_class_of_pair(m, True, beam_sign)
    if internal_state == EXCITED:
        return _ground_class_of_pair(m, False, beam_sign)
    raise ValueError(f"internal_state must be 'g' or 'e', got {internal_state!r}")


def opll_m_term_hz(
    m: int,
    internal_state: InternalState,
    beam_sign: int,
    kick_hz: float = constants.MOMENTUM_KICK_DETUNING,
) -> float:
    """Static m-dependent term of the OPLL frequency for an LMT pulse.

    This is the atomic-frame detuning of the addressed pair,
    :func:`transition_detuning_hz`, to be used in the kernel formula (see module
    docstring).

    Args:
        m:              Momentum class of the populated state being addressed.
        internal_state: Internal state (:data:`GROUND` or :data:`EXCITED`) of
                        that population.
        beam_sign:      Beam direction, +1 (up) or -1 (down). kick_hz: Doppler shift
                        per photon recoil.

    Returns:
        Frequency term in Hz.
    """
    m_g = pair_ground_class(m, internal_state, beam_sign)
    return transition_detuning_hz(m_g, beam_sign, kick_hz=kick_hz)


# ── Recorded-intent vocabulary ────────────────────────────────────────────────


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
