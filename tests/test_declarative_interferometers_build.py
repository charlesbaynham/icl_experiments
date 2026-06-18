"""
Structural build check for the D4/D5 declarative interferometer fragments.

This complements tests/test_compile_all.py. The shared EMGain *parameter*
defaults to enabled (em_gain_enabled=True), which - against a fresh mock
dataset DB where the DISABLE_EM_GAIN safety interlock reads its True default -
trips the interlock in host_setup() for every declarative-LMT fragment
(D3 included, on this branch). That is a pre-existing environment condition,
not a defect in these fragments and unrelated to their sequence/MRO/hooks.

To exercise the build path of D4/D5 (MRO, both kernel hooks, the spawned
per-pulse ndscan parameters) without depending on the interlock dataset, this
test overrides only the ordinary em_gain_enabled parameter to False ("do not
use EM gain"), which never trips the interlock. It does NOT read, write, set or
otherwise touch the DISABLE_EM_GAIN interlock dataset.
"""

import pytest

from repository.LMT.declarative_interferometers import DeclarativeLMTDualMachZehnderFrag
from repository.LMT.declarative_interferometers import (
    DeclarativeLMTSingleInterferometerFrag,
)


@pytest.mark.parametrize(
    "frag",
    [DeclarativeLMTSingleInterferometerFrag, DeclarativeLMTDualMachZehnderFrag],
    ids=["D5_single", "D4_dual"],
)
def test_fragment_builds_with_em_gain_disabled(frag, fragment_factory):
    exp = fragment_factory(frag)
    # Override the EMGain parameter (not the interlock dataset) so host_setup
    # does not require the DISABLE_EM_GAIN interlock to be cleared.
    exp.override_param("em_gain_enabled", False)
    exp.host_setup()
    # The declarative engine spawned the per-pulse parameters from the compiled
    # sequence; confirm the per-event handle arrays match the sequence length.
    assert exp._lmt_n_events == len(frag.lmt_sequence)
    assert len(exp._lmt_offset_handles) == exp._lmt_n_events
    assert len(exp._lmt_duration_handles) == exp._lmt_n_events
