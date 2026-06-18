"""
Host-side closure assertions for the split (D4) and LMT (D5) declarative
interferometers, mirroring tests/test_lmt_sequence.py::
test_mach_zehnder_compiles_and_closes.

These check the pure-host momentum-class bookkeeping (no ARTIQ): each declared
sequence compiles and its final population is exactly the expected output
ports. test_compile_all.py separately checks the fragments build with their
default ndscan params.
"""

from repository.lib.lmt_sequence import compile_sequence
from repository.LMT.declarative_interferometers import DeclarativeLMTDualMachZehnderFrag
from repository.LMT.declarative_interferometers import (
    DeclarativeLMTSingleInterferometerFrag,
)
from repository.LMT.declarative_interferometers import _full_intensity_setpoint
from repository.LMT.declarative_interferometers import build_single_lmt_interferometer
from repository.LMT.lmt_declarative import M_TOP


def _compile(frag):
    return compile_sequence(
        list(frag.lmt_sequence),
        initial_population=set(frag.lmt_initial_population),
    )


def test_dual_mach_zehnder_closes_to_four_ports():
    """D4: after the split + separation the two clouds are far apart in momentum;
    each runs its own Mach-Zehnder, so the sequence closes to four distinct ports
    - two per cloud. The lower cloud's pair sits at (M_TOP-1, M_TOP); the upper
    cloud's pair sits N_SEP recoils higher."""
    from repository.LMT.declarative_interferometers import N_SEP

    compiled = _compile(DeclarativeLMTDualMachZehnderFrag)
    ports = compiled.final_population
    # Exactly four ports, all at distinct momentum classes (spatially resolvable).
    assert len(ports) == 4
    assert len({m for _state, m in ports}) == 4
    # Lower interferometer ports.
    assert ("g", M_TOP - 1) in ports
    assert ("e", M_TOP) in ports
    # Upper interferometer is N_SEP recoils above; its two ports straddle the
    # upper cloud's momentum class.
    upper_ms = sorted(m for _state, m in ports if m > M_TOP)
    assert upper_ms[-1] - upper_ms[0] == 1  # a g/e port pair
    assert upper_ms[0] >= M_TOP + N_SEP  # genuinely separated from the lower cloud


def test_single_lmt_interferometer_closes_to_two_ports():
    """D5: the LMT Mach-Zehnder closes to the same two ports as the D3 MZ,
    regardless of the arm-opening depth N_BS."""
    compiled = _compile(DeclarativeLMTSingleInterferometerFrag)
    assert compiled.final_population == frozenset({("e", M_TOP), ("g", M_TOP + 1)})


def test_single_lmt_interferometer_closes_for_all_depths():
    """The wide-arm geometry closes for every N_BS; N_BS == 1 is the plain MZ.
    This is the geometry Agent-C mirrors for the dual LMT interferometer."""
    target = frozenset({("e", M_TOP), ("g", M_TOP + 1)})
    for n_bs in (1, 2, 3, 4, 6, 8):
        seq = [_full_intensity_setpoint()] + build_single_lmt_interferometer(
            n_bs, m_top=M_TOP
        )
        compiled = compile_sequence(seq, initial_population={("e", M_TOP)})
        assert compiled.final_population == target, (
            n_bs,
            sorted(compiled.final_population),
        )


def test_single_lmt_interferometer_arm_makes_excursion():
    """The moving arm genuinely climbs N_BS recoils above the parked arm
    (a real LMT excursion), then returns - not a near-stationary oscillation."""
    n_bs = 4
    seq = [_full_intensity_setpoint()] + build_single_lmt_interferometer(
        n_bs, m_top=M_TOP
    )
    # Walk the population through the opening ladder and check the moving arm
    # reaches m_top + n_bs while the parked arm stays at (e, M_TOP).
    max_m = M_TOP
    for k in range(1, len(seq) + 1):
        compiled = compile_sequence(seq[:k], initial_population={("e", M_TOP)})
        assert ("e", M_TOP) in compiled.final_population
        for state, m in compiled.final_population:
            max_m = max(max_m, m)
    assert max_m == M_TOP + n_bs
