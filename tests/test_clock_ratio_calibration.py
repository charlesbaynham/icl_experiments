"""
Tests for the declarative clock Rabi / set-point ratio calibration sequence.

The physics check that matters: the same-beam probe must address the velocity
class the slice selected and drive it back to ``(g, 0)``, so the fitted Rabi
flop reflects the probe pulse alone.
"""

import pytest

from repository.lib import constants
from repository.lib.lmt_sequence import EVENT_CLEAROUT
from repository.lib.lmt_sequence import EVENT_PULSE
from repository.lib.lmt_sequence import EVENT_SETPOINT
from repository.lib.lmt_sequence import Beam
from repository.lib.lmt_sequence import compile_sequence
from repository.lib.physics.lmt_resonance import GROUND
from repository.LMT.lmt_clock_ratio_calibration import _ratio_cal_sequence


@pytest.mark.parametrize(
    "beam, probe_pi_time",
    [
        (Beam.UP, constants.CLOCK_PI_TIME),
        (Beam.DOWN, constants.DOWN_CLOCK_BEAM_PI_TIME),
    ],
)
def test_ratio_cal_sequence_returns_to_ground(beam, probe_pi_time):
    sequence = _ratio_cal_sequence(beam)
    compiled = compile_sequence(sequence, initial_population={(GROUND, 0)})

    # slice + clearout + probe takes the selected class straight back to (g, 0):
    # (g, 0) --slice--> (e, beam.sign) --probe--> (g, 0).
    assert compiled.final_population == frozenset({(GROUND, 0)})

    kinds = [e.kind for e in compiled.events]
    assert kinds == [
        EVENT_SETPOINT,  # slice set point
        EVENT_PULSE,  # slice
        EVENT_CLEAROUT,  # blast unselected ground state
        EVENT_SETPOINT,  # probe (operating) set point = V_ref
        EVENT_PULSE,  # probe
    ]

    # The probe is governed by the operating (second) set point, and its default
    # duration follows that set point's declared per-beam Rabi -> the pi time we
    # are calibrating. Scanning p04_pi_probe_duration sweeps the flop.
    probe = compiled.events[4]
    assert probe.governing_setpoint_index == 3
    assert probe.duration_param.default == pytest.approx(probe_pi_time)


def test_ratio_cal_slice_is_the_shelving_pulse():
    """The slice keeps the fixed shelving set point / duration (not recalibrated)."""
    compiled = compile_sequence(
        _ratio_cal_sequence(Beam.UP), initial_population={(GROUND, 0)}
    )
    slice_setpoint = compiled.events[0]
    slice_pulse = compiled.events[1]
    assert slice_setpoint.setpoint_param.default == pytest.approx(
        constants.CLOCK_SHELVING_PULSE_SETPOINT
    )
    assert slice_pulse.duration_param.default == pytest.approx(
        constants.CLOCK_SHELVING_PULSE_TIME
    )
