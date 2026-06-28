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
