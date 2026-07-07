"""
Unit tests for the free-fall gravity Doppler applied to the clock-pulse readout.

The readout DOWN pi (``NormalisedFastKineticsClockPulseMixin.do_first_pulse``)
fires with the OPLL reset to ``start_opll_offset`` by the ladder, but the atoms
are still falling. ``prepare_readout_opll_hook`` must therefore move the OPLL to
the free-fall resonance the ladder DOWN pulses carry - and only on the
LMT-corrected path (the plain ``ClockSpectroscopyBase`` consumers have no OPLL
tracker, so the hook is a no-op there).

We drive the real (unwrapped) hook against a lightweight object that captures
the ``set_clock_opll`` call; the arithmetic under test is pure Python.
"""

import pytest
from numpy import int64

from repository.lib import constants
from repository.lib.experiment_templates.mixins.andor_imaging.lmt_compensated_normalised_imaging import (  # noqa: E501
    _READOUT_BEAM_SIGN,
    _START_OPLL_OFFSET,
    NormalisedFastKineticsLMTCorrectedClockMixin,
)
from repository.lib.experiment_templates.mixins.andor_imaging.normalised_fast_kinetics_base import (  # noqa: E501
    NormalisedFastKineticsClockPulseMixin,
)


def _raw(method):
    return method.artiq_embedded.function


_lmt_hook = _raw(NormalisedFastKineticsLMTCorrectedClockMixin.prepare_readout_opll_hook)
_base_hook = _raw(NormalisedFastKineticsClockPulseMixin.prepare_readout_opll_hook)


class _LMTReadout:
    """Stands in for the LMT-corrected experiment: a real core, a release
    timestamp and a capturing ``set_clock_opll``."""

    prepare_readout_opll_hook = _lmt_hook

    def __init__(self, core, t_release_mu):
        self.core = core
        self._t_release_mu = int64(t_release_mu)
        self.opll_calls = []

    def get_t_release_mu(self):
        return self._t_release_mu

    def set_clock_opll(self, freq):
        self.opll_calls.append(freq)


class _BaseReadout:
    """Stands in for a plain ClockSpectroscopyBase consumer: no OPLL tracker."""

    prepare_readout_opll_hook = _base_hook

    def __init__(self):
        self.opll_calls = []

    def set_clock_opll(self, freq):  # would blow up the base path if ever called
        self.opll_calls.append(freq)


def _expected(t_fall_s):
    return (
        _START_OPLL_OFFSET
        + _READOUT_BEAM_SIGN * t_fall_s * constants.GRAVITY_DOPPLER_PER_SEC_CLOCK
    )


def test_readout_opll_includes_gravity_for_nonzero_fall(device_mgr, monkeypatch):
    core = device_mgr.get("core")

    t_release_mu = int64(1_000_000)
    t_fall_s = 6.766e-3
    now_mu = t_release_mu + core.seconds_to_mu(t_fall_s)
    monkeypatch.setattr(
        "repository.lib.experiment_templates.mixins.andor_imaging."
        "lmt_compensated_normalised_imaging.now_mu",
        lambda: now_mu,
    )

    outer = _LMTReadout(core, t_release_mu)
    outer.prepare_readout_opll_hook()

    assert len(outer.opll_calls) == 1
    # The exact fall time the core actually round-trips through mu.
    t_fall_actual = core.mu_to_seconds(now_mu - t_release_mu)
    assert outer.opll_calls[0] == _expected(t_fall_actual)

    # The gravity term must actually move the OPLL: DOWN readout at ~6.77 ms
    # fall is ~95 kHz below the reset offset.
    assert outer.opll_calls[0] != _START_OPLL_OFFSET
    assert outer.opll_calls[0] - _START_OPLL_OFFSET < 0.0  # DOWN beam -> red shift
    assert (_START_OPLL_OFFSET - outer.opll_calls[0]) / 1e3 == pytest.approx(
        95.0, abs=1.0
    )


def test_readout_opll_zero_fall_stays_at_offset(device_mgr, monkeypatch):
    core = device_mgr.get("core")

    t_release_mu = int64(2_000_000)
    monkeypatch.setattr(
        "repository.lib.experiment_templates.mixins.andor_imaging."
        "lmt_compensated_normalised_imaging.now_mu",
        lambda: t_release_mu,
    )

    outer = _LMTReadout(core, t_release_mu)
    outer.prepare_readout_opll_hook()

    assert outer.opll_calls == [_START_OPLL_OFFSET]


def test_base_path_is_noop():
    """The non-LMT base hook must not touch the OPLL (no tracker exists)."""
    outer = _BaseReadout()
    outer.prepare_readout_opll_hook()
    assert outer.opll_calls == []
