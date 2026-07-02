"""
Tests for the initial-velocity (v0) Doppler term tethering in the declarative
LMT engine.

The v0 term must be tethered to the *first pulse* of the sequence: that pulse
selects the velocity class, so it carries no v0 term, and every other pulse is
corrected differentially against it. On the canonical ev0-ev4 symmetric-MZ
sequence (SetPoint[slice], pi(UP, m=0)[slice], SetPoint[full], Clearout,
ladder(DOWN, n=1)) the up slice (ev1) therefore gets v0 contribution 0 and the
down ladder pulse (ev4) gets +2*v0/lambda.

These are pure host-side checks: the sequence is compiled with the pure
compiler and the engine's array-assembly hook is driven on a bare mixin
instance (build skipped), exactly as in ``test_lmt_global_params``.
"""

import pytest

from repository.lib import constants
from repository.lib.lmt_sequence import Beam
from repository.lib.lmt_sequence import Clearout
from repository.lib.lmt_sequence import SetPoint
from repository.lib.lmt_sequence import compile_sequence
from repository.lib.lmt_sequence import ladder
from repository.lib.lmt_sequence import pi
from repository.lib.physics.lmt_resonance import GROUND

INV_LAMBDA = 1.0 / constants.CLOCK_WAVELENGTH_M


def _canonical_sequence():
    """The compiled ev0-ev4 sequence of DeclarativeLMTSymmetricMachZehnder
    (N_LAUNCH = 1): slice setpoint, up slice, full setpoint, clearout, one
    down ladder pulse."""
    sequence = [
        SetPoint(setpoint=0.012, rabi_up=1.0 / (2 * 380e-6), label="slice"),
        pi(Beam.UP, m=0, label="slice"),
        SetPoint(setpoint=2.6, rabi_up=9e3, rabi_down=7e3),
        Clearout(),
        *ladder(start_m=1, n=1, first_beam=Beam.DOWN),
    ]
    return compile_sequence(sequence, initial_population={(GROUND, 0)})


def _assemble(compiled):
    """Drive the engine's array-assembly hook on a bare instance.

    The slot-binding helpers need a built ndscan fragment, so they are stubbed
    to no-ops: this test only exercises the v0 reference + per-event beam-sign
    bookkeeping, which is what feeds the kernel v0 formula.
    """
    from repository.lib.experiment_templates.mixins.declarative_lmt import (
        DeclarativeLMTBase,
    )

    inst = object.__new__(DeclarativeLMTBase)
    inst._bind_offset_slot = lambda event: None
    inst._bind_duration_slot = lambda event: None
    inst._bind_setpoint_slot = lambda event: None
    inst._bind_phase_slot = lambda event: None
    inst._bind_rabi_slot = lambda event: None
    inst._lmt_assemble_event_arrays(compiled)
    return inst


def _kernel_v0_term(inst, i, v0):
    """The v0 contribution the kernel formula adds for event ``i`` at velocity
    ``v0`` (the tethered differential term)."""
    return (inst._lmt_v0_reference_beam_sign - inst._lmt_beam_sign[i]) * v0 * INV_LAMBDA


def test_reference_beam_sign_is_first_pulse():
    """s_ref is the beam sign of the first PULSE event (the up slice -> +1),
    not of the leading SetPoint."""
    inst = _assemble(_canonical_sequence())
    # The slice pulse (ev1) is the first pulse and is up; the leading SetPoint
    # (ev0) is not a pulse and must not set the reference.
    assert inst._lmt_v0_reference_beam_sign == pytest.approx(1.0)


def test_up_slice_carries_no_v0_down_pulse_carries_double():
    """On the canonical sequence: up slice (ev1) v0 term == 0, down ladder
    pulse (ev4) v0 term == +2*v0/lambda."""
    v0 = constants.DEFAULT_INITIAL_VELOCITY_M_S
    inst = _assemble(_canonical_sequence())

    # ev1 is the up slice, ev4 the down ladder pulse
    assert inst._lmt_beam_sign[1] == pytest.approx(1.0)
    assert inst._lmt_beam_sign[4] == pytest.approx(-1.0)

    assert _kernel_v0_term(inst, 1, v0) == pytest.approx(0.0)
    assert _kernel_v0_term(inst, 4, v0) == pytest.approx(2.0 * v0 * INV_LAMBDA)
    # ~ +40 kHz at the default ~14 mm/s
    assert _kernel_v0_term(inst, 4, v0) == pytest.approx(40.0e3, abs=0.4e3)


def test_changing_v0_moves_down_not_up():
    """Recomputing at two v0 values moves the down pulse by 2*dv0/lambda and
    leaves the up slice unmoved (the headline on-atom prediction)."""
    inst = _assemble(_canonical_sequence())
    v0_a, v0_b = 0.0, 14e-3  # mm/s -> m/s
    dv = v0_b - v0_a

    d_up = _kernel_v0_term(inst, 1, v0_b) - _kernel_v0_term(inst, 1, v0_a)
    d_down = _kernel_v0_term(inst, 4, v0_b) - _kernel_v0_term(inst, 4, v0_a)

    assert d_up == pytest.approx(0.0)
    assert d_down == pytest.approx(2.0 * dv * INV_LAMBDA)
    # Slope 2/lambda = 2.865 kHz per mm/s
    assert d_down / (dv * 1e3) == pytest.approx(2.865e3, abs=10.0)


def test_slice_offset_shift_versus_pre_fix():
    """The fix changes the slice v0 term from -v0/lambda (old, wrong) to 0, so
    at the default v0 the slice OPLL moves by +v0/lambda (~+20 kHz) versus the
    pre-fix code - the documented caveat for re-finding the slice line."""
    v0 = constants.DEFAULT_INITIAL_VELOCITY_M_S
    inst = _assemble(_canonical_sequence())
    old_slice_term = -inst._lmt_beam_sign[1] * v0 * INV_LAMBDA  # pre-fix formula
    new_slice_term = _kernel_v0_term(inst, 1, v0)
    shift = new_slice_term - old_slice_term
    assert shift == pytest.approx(+v0 * INV_LAMBDA)
    assert shift == pytest.approx(20.0e3, abs=0.4e3)
