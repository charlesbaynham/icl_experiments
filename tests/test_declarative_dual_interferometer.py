"""
Host-side closure assertions for the dual (gradiometer) LMT interferometer
(deliverable D6), mirroring tests/test_lmt_sequence.py and
tests/test_declarative_interferometers.py.

These check the pure-host momentum-class bookkeeping (no ARTIQ): the declared
sequence compiles and its final population is exactly the four expected output
ports (two per cloud). test_compile_all.py separately checks the fragment
builds with its default ndscan params.
"""

from repository.lib.lmt_sequence import compile_sequence
from repository.LMT.declarative_dual_interferometer import (
    DeclarativeLMTDualInterferometerFrag,
)
from repository.LMT.declarative_dual_interferometer import (
    build_dual_lmt_interferometer,
)
from repository.LMT.declarative_dual_interferometer import _slice_launch_prefix
from repository.LMT.declarative_dual_interferometer import N_BS


def _compile(frag):
    return compile_sequence(
        list(frag.lmt_sequence),
        initial_population=set(frag.lmt_initial_population),
    )


def test_dual_interferometer_closes_to_four_ports():
    """D6: the two interferometers close to four distinct ports - two per
    cloud (the lower and upper clouds' output pairs)."""
    _seq, m_lo, m_hi = build_dual_lmt_interferometer(N_BS)
    expected = frozenset({("e", m_lo), ("g", m_lo + 1), ("e", m_hi), ("g", m_hi + 1)})
    compiled = _compile(DeclarativeLMTDualInterferometerFrag)
    assert compiled.final_population == expected


def test_dual_interferometer_closes_for_all_depths():
    """The dual wide-arm geometry closes for every N_BS; the clouds are kept
    far enough apart that their LMT arms never overlap in momentum."""
    for n_bs in (1, 2, 3, 4, 6, 8):
        seq, m_lo, m_hi = build_dual_lmt_interferometer(n_bs)
        compiled = compile_sequence(
            [*_slice_launch_prefix(), *seq], initial_population={("g", 0)}
        )
        expected = frozenset(
            {("e", m_lo), ("g", m_lo + 1), ("e", m_hi), ("g", m_hi + 1)}
        )
        assert compiled.final_population == expected, (
            n_bs,
            sorted(compiled.final_population),
        )


def test_two_clouds_separate_in_momentum():
    """The separation step opens a real velocity gap between the two clouds so
    they resolve spatially: the upper cloud's parked arm sits well above the
    lower (>= 2 * N_BS + 1 recoils), not one recoil away."""
    for n_bs in (1, 2, 4, 8):
        _seq, m_lo, m_hi = build_dual_lmt_interferometer(n_bs)
        assert m_hi - m_lo >= 2 * n_bs + 1, (n_bs, m_lo, m_hi)
