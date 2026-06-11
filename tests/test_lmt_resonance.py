"""
Tests for the LMT resonance predictor.

The critical test here is the sign anchor: the new model formula

    f_opll = START + s * D - opll_m_term_hz(m, state, s) + offset

must reproduce the empirically-verified frequencies of the legacy LMT loop
formulas (``up_pulse`` / ``down_pulse`` / ``launch_series`` / ``lmt_series``
in ``LMT_launch_mixins.py``) up to the constant recoil-energy term
``-s * kick / 2`` which the legacy code omits (it is absorbed there into the
empirical offset parameters).
"""

import pytest

from repository.lib import constants
from repository.lib.lmt_sequence import Beam
from repository.lib.lmt_sequence import SetPoint
from repository.lib.lmt_sequence import compile_sequence
from repository.lib.lmt_sequence import ladder
from repository.lib.physics import lmt_resonance

KICK = constants.MOMENTUM_KICK_DETUNING
START = 80e6  # OPLL offset DDS centre frequency


def test_recoil_constants():
    """First-principles recoil constants agree with the calibrated values."""
    assert lmt_resonance.RECOIL_FREQUENCY_HZ == pytest.approx(4.7e3, rel=0.01)
    assert lmt_resonance.DOPPLER_PER_KICK_HZ == pytest.approx(
        constants.MOMENTUM_KICK_DETUNING, rel=0.005
    )
    # The kick is the single-photon Doppler shift of one recoil velocity
    import scipy.constants

    v_recoil = scipy.constants.h / (
        constants.SR_ATOM_MASS_KG * constants.CLOCK_WAVELENGTH_M
    )
    assert lmt_resonance.DOPPLER_PER_KICK_HZ == pytest.approx(
        v_recoil / constants.CLOCK_WAVELENGTH_M, rel=1e-9
    )


@pytest.mark.parametrize("k_sign", [1, -1])
@pytest.mark.parametrize("m", range(-5, 6))
def test_addressed_class_round_trip(m, k_sign):
    detuning = lmt_resonance.transition_detuning_hz(m, k_sign)
    assert lmt_resonance.addressed_ground_class(detuning, k_sign) == pytest.approx(m)


@pytest.mark.parametrize("beam_sign", [1, -1])
def test_pair_ground_class(beam_sign):
    # Driving a ground state addresses the pair rooted at that state
    assert lmt_resonance.pair_ground_class(3, "g", beam_sign) == 3
    # Driving an excited state |e, m> addresses |g, m - s> <-> |e, m>
    assert lmt_resonance.pair_ground_class(3, "e", beam_sign) == 3 - beam_sign


def test_invalid_arguments():
    with pytest.raises(ValueError):
        lmt_resonance.transition_detuning_hz(0, 0)
    with pytest.raises(ValueError):
        lmt_resonance.addressed_ground_class(0.0, 2)
    with pytest.raises(ValueError):
        lmt_resonance.pair_ground_class(0, "x", 1)


# ---------------------------------------------------------------------------
# Legacy formula references (transcribed from LMT_launch_mixins.py)
# ---------------------------------------------------------------------------


def legacy_up_pulse(doppler, n_previous):
    """LMTBase.up_pulse"""
    return START + doppler - n_previous * KICK


def legacy_down_pulse(doppler, n_previous):
    """LMTBase.down_pulse"""
    return START - doppler + n_previous * KICK


def legacy_launch_series(doppler, n_previous, n):
    """LMTBase.launch_series / lmt_series: starts with a down pulse on
    excited atoms. Returns (frequency, is_up) per pulse."""
    out = []
    for i in range(n):
        is_up = i % 2 == 1
        f = START + (-1) ** (i + 1) * doppler + (i + n_previous) * (-1) ** i * KICK
        out.append((f, is_up))
    return out


def legacy_series_start_up(doppler, n_previous, n):
    """LMTBase.lmt_series_start_up: starts with an up pulse on ground atoms."""
    out = []
    for i in range(n):
        is_up = i % 2 == 0
        f = START + (-1) ** i * doppler + (i + n_previous) * (-1) ** (i + 1) * KICK
        out.append((f, is_up))
    return out


def new_pulse_frequency(doppler, compiled_event):
    """The kernel formula of the declarative stack, evaluated host-side."""
    s = compiled_event.beam_sign
    return START + s * doppler - compiled_event.m_term_hz


def _compile_ladder(start_m, n, first_beam, initial_population):
    sequence = [
        SetPoint(setpoint=2.6, rabi_up=9e3, rabi_down=7e3),
        *ladder(start_m=start_m, n=n, first_beam=first_beam),
    ]
    compiled = compile_sequence(sequence, initial_population=initial_population)
    return [e for e in compiled.events if e.kind == 0]  # pulses only


@pytest.mark.parametrize("doppler", [0.0, 1.23e6])
@pytest.mark.parametrize("n_previous", [1, 5, 13])
def test_launch_ladder_matches_legacy(doppler, n_previous):
    """A down-first ladder on excited atoms reproduces launch_series up to
    the recoil-energy constant -s * kick / 2."""
    n = 8
    pulses = _compile_ladder(
        start_m=n_previous,
        n=n,
        first_beam=Beam.DOWN,
        initial_population={("e", n_previous)},
    )
    legacy = legacy_launch_series(doppler, n_previous, n)
    assert len(pulses) == len(legacy)
    for event, (f_legacy, is_up_legacy) in zip(pulses, legacy):
        assert (event.beam_sign == 1) == is_up_legacy
        f_new = new_pulse_frequency(doppler, event)
        recoil_correction = -event.beam_sign * KICK / 2.0
        assert f_new == pytest.approx(f_legacy + recoil_correction, abs=1e-6)


@pytest.mark.parametrize("doppler", [0.0, 2.5e6])
@pytest.mark.parametrize("n_previous", [2, 7])
def test_ground_start_ladder_matches_legacy(doppler, n_previous):
    """An up-first ladder on ground atoms reproduces lmt_series_start_up up
    to the recoil-energy constant."""
    n = 6
    pulses = _compile_ladder(
        start_m=n_previous,
        n=n,
        first_beam=Beam.UP,
        initial_population={("g", n_previous)},
    )
    legacy = legacy_series_start_up(doppler, n_previous, n)
    assert len(pulses) == len(legacy)
    for event, (f_legacy, is_up_legacy) in zip(pulses, legacy):
        assert (event.beam_sign == 1) == is_up_legacy
        f_new = new_pulse_frequency(doppler, event)
        recoil_correction = -event.beam_sign * KICK / 2.0
        assert f_new == pytest.approx(f_legacy + recoil_correction, abs=1e-6)


def test_single_pulses_match_legacy_helpers():
    """up_pulse / down_pulse equivalence: legacy N_previous is the momentum
    index of the state the atoms occupy."""
    doppler = 0.7e6
    # up_pulse fires on ground atoms at m = N
    for n in [0, 3, 12]:
        m_term = lmt_resonance.opll_m_term_hz(n, "g", 1)
        f_new = START + doppler - m_term
        assert f_new == pytest.approx(legacy_up_pulse(doppler, n) - KICK / 2.0)
    # down_pulse fires on excited atoms at m = N
    for n in [1, 4, 13]:
        m_term = lmt_resonance.opll_m_term_hz(n, "e", -1)
        f_new = START - doppler - m_term
        assert f_new == pytest.approx(legacy_down_pulse(doppler, n) + KICK / 2.0)


def test_first_beam_splitter_anchor():
    """The legacy interferometer beam splitter (down beam, after an N-pulse
    launch from the single shelving kick) used an OPLL m-term of
    +(N_launch + 1) * kick; the new formula gives the same up to +kick/2.

    This pins the initial-population anchor {("e", 1)} after shelving.
    """
    n_launch = 12
    # After the launch the atoms are excited at m = 1 + n_launch
    m = 1 + n_launch
    m_term = lmt_resonance.opll_m_term_hz(m, "e", -1)
    # Legacy: calculate_frequency_for_first_pi_by_2_pulse contributes
    # (-chirp + kick) and first_beam_splitter adds n_launch * kick.
    legacy_m_contribution = (1 + n_launch) * KICK
    assert -m_term == pytest.approx(legacy_m_contribution + KICK / 2.0)
