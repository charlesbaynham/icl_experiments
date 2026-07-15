"""
Unit tests for the free-fall gravity Doppler applied to the clock-pulse readout.

The readout DOWN pi (``NormalisedFastKineticsClockPulseMixin.do_first_pulse``)
fires with the OPLL reset to ``start_opll_offset`` by the ladder, but the atoms
are still falling. ``_set_readout_opll_for_fall`` must therefore move the OPLL
to the free-fall resonance the ladder DOWN pulses carry.

We drive the real (unwrapped) kernel method against a lightweight object that captures
the ``set_clock_opll`` call; the arithmetic under test is pure Python.
"""

import pytest
from numpy import int64

from repository.lib import constants
from repository.lib.experiment_templates.mixins.andor_imaging.normalised_fast_kinetics_base import (  # noqa: E501
    READOUT_BEAM_SIGN,
)
from repository.lib.experiment_templates.mixins.andor_imaging.normalised_fast_kinetics_base import (
    READOUT_START_OPLL_OFFSET,
)
from repository.lib.experiment_templates.mixins.andor_imaging.normalised_fast_kinetics_base import (
    NormalisedFastKineticsClockPulseMixin,
)


def _raw(method):
    return method.artiq_embedded.function


_set_readout_opll_for_fall = _raw(
    NormalisedFastKineticsClockPulseMixin._set_readout_opll_for_fall
)


class _Readout:
    """Stand-in object with a real core and capturing ``set_clock_opll``."""

    _set_readout_opll_for_fall = _set_readout_opll_for_fall

    def __init__(self, core, t_release_mu):
        self.core = core
        self._t_release_mu = int64(t_release_mu)
        self.opll_calls = []

    def get_t_release_mu(self):
        return self._t_release_mu

    def set_clock_opll(self, freq):
        self.opll_calls.append(freq)


def _expected(t_fall_s):
    return (
        READOUT_START_OPLL_OFFSET
        + READOUT_BEAM_SIGN * t_fall_s * constants.GRAVITY_DOPPLER_PER_SEC_CLOCK
    )


def test_readout_opll_includes_gravity_for_nonzero_fall(device_mgr, monkeypatch):
    core = device_mgr.get("core")

    t_release_mu = int64(1_000_000)
    t_fall_s = 6.766e-3
    now_mu = t_release_mu + core.seconds_to_mu(t_fall_s)
    monkeypatch.setattr(
        "repository.lib.experiment_templates.mixins.andor_imaging."
        "normalised_fast_kinetics_base.now_mu",
        lambda: now_mu,
    )

    outer = _Readout(core, t_release_mu)
    outer._set_readout_opll_for_fall()

    assert len(outer.opll_calls) == 1
    # The exact fall time the core actually round-trips through mu.
    t_fall_actual = core.mu_to_seconds(now_mu - t_release_mu)
    assert outer.opll_calls[0] == _expected(t_fall_actual)

    # The gravity term must actually move the OPLL: DOWN readout at ~6.77 ms
    # fall is ~95 kHz below the reset offset.
    assert outer.opll_calls[0] != READOUT_START_OPLL_OFFSET
    assert (
        outer.opll_calls[0] - READOUT_START_OPLL_OFFSET < 0.0
    )  # DOWN beam -> red shift
    assert (READOUT_START_OPLL_OFFSET - outer.opll_calls[0]) / 1e3 == pytest.approx(
        95.0, abs=1.0
    )


def test_readout_opll_zero_fall_stays_at_offset(device_mgr, monkeypatch):
    core = device_mgr.get("core")

    t_release_mu = int64(2_000_000)
    monkeypatch.setattr(
        "repository.lib.experiment_templates.mixins.andor_imaging."
        "normalised_fast_kinetics_base.now_mu",
        lambda: t_release_mu,
    )

    outer = _Readout(core, t_release_mu)
    outer._set_readout_opll_for_fall()

    assert outer.opll_calls == [READOUT_START_OPLL_OFFSET]
