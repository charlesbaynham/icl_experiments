"""Host-side validation of the ROI-predictor diagnostic experiment.

These tests do NOT touch the live rig or the EM-gain safety interlock
(``DISABLE_EM_GAIN``): they only build the fragments and walk the declared
sequences on the host.
"""

import pytest

from repository.lib.lmt_sequence import compile_sequence
from repository.LMT import roi_prediction_check as rpc

# ── Momentum / closure: compile the declared sequences on the host ────────────


def _final_population(frag_cls):
    compiled = compile_sequence(
        list(frag_cls.lmt_sequence),
        initial_population=set(frag_cls.lmt_initial_population),
        strict=True,
    )
    return sorted(compiled.final_population)


def test_fall_imparts_no_momentum():
    # Free fall: the single ground branch stays at momentum class 0.
    assert _final_population(rpc.RoiCheckFall) == [("g", 0)]


def test_up_ends_at_plus_n_ground():
    # Upward ladder: a single clean ground branch at +N.
    assert _final_population(rpc.RoiCheckUp) == [("g", rpc.N_RECOILS)]


def test_down_ends_at_minus_n_ground():
    # Downward ladder: a single clean ground branch at -N.
    assert _final_population(rpc.RoiCheckDown) == [("g", -rpc.N_RECOILS)]


def test_up_and_down_are_equal_and_opposite():
    up = _final_population(rpc.RoiCheckUp)
    down = _final_population(rpc.RoiCheckDown)
    assert up[0][1] == -down[0][1]
    assert rpc.N_RECOILS > 0
    # Even number of recoils so the final state is ground (clean single cloud).
    assert rpc.N_RECOILS % 2 == 0


def test_single_branch_at_imaging_for_all_variants():
    # Every variant must leave exactly one populated branch so the ROI tracks a
    # single cloud, not a smear of several.
    for frag_cls in (rpc.RoiCheckFall, rpc.RoiCheckUp, rpc.RoiCheckDown):
        assert len(_final_population(frag_cls)) == 1


def test_sliced_ends_at_plus_two_ground():
    # The velocity-sliced variant: slice pi (+1 recoil) then launch pi (+1)
    # leaves a single clean ground branch at +2 - a clean 2-recoil launch.
    assert _final_population(rpc.RoiCheckUp2Sliced) == [("g", 2)]


def test_sliced_baseline_ends_at_zero_ground():
    # The no-net-launch baseline: slice pi (+1 recoil) then return pi (-1)
    # leaves a single clean ground branch at 0 - the matched zero-momentum
    # control for the 2-recoil launch.
    assert _final_population(rpc.RoiCheckSlicedBaseline) == [("g", 0)]


def test_sliced_launch_ladder_end_states():
    # Configurable sliced launch ladder, built ONE LMT at a time after the
    # slice + clearout (the first DOWN pulse is n=1). The single populated
    # branch walks |e,+1> -> m=n+1: ground for odd n, excited for even n.
    assert _final_population(rpc.RoiCheckSlicedLaunch1) == [("g", 2)]
    assert _final_population(rpc.RoiCheckSlicedLaunch2) == [("e", 3)]
    assert _final_population(rpc.RoiCheckSlicedLaunch3) == [("g", 4)]


def test_sliced_launch_n1_matches_existing_sliced():
    # The n=1 sliced launch is the same construction as RoiCheckUp2Sliced.
    assert _final_population(rpc.RoiCheckSlicedLaunch1) == _final_population(
        rpc.RoiCheckUp2Sliced
    )


def test_sliced_launch_single_branch():
    # Every n leaves exactly one populated branch so the ROI tracks one cloud.
    for cls in (
        rpc.RoiCheckSlicedLaunch1,
        rpc.RoiCheckSlicedLaunch2,
        rpc.RoiCheckSlicedLaunch3,
    ):
        assert len(_final_population(cls)) == 1


def test_sliced_baseline_matches_launch_pulse_count():
    # The baseline must have the SAME number of declared events as the launch
    # variant so the two sequences have matched duration; differencing them
    # isolates exactly the launch recoils.
    assert len(rpc.RoiCheckSlicedBaseline.lmt_sequence) == len(
        rpc.RoiCheckUp2Sliced.lmt_sequence
    )


# ── Structural build: construct each fragment with mocked managers ────────────
# init_params() runs build_fragment + parameter wiring but never host_setup, so
# the EM-gain interlock dataset is never read or written here.


@pytest.mark.parametrize(
    "frag_cls",
    [
        rpc.RoiCheckFall,
        rpc.RoiCheckUp,
        rpc.RoiCheckDown,
        rpc.RoiCheckUp2Sliced,
        rpc.RoiCheckSlicedBaseline,
        rpc.RoiCheckSlicedLaunch1,
        rpc.RoiCheckSlicedLaunch2,
        rpc.RoiCheckSlicedLaunch3,
    ],
)
def test_fragment_builds_and_exposes_flight_time(fragment_factory, frag_cls):
    frag = fragment_factory(frag_cls)

    # The scannable wait param exists and is reused by the Wait event.
    assert hasattr(frag, "flight_time")

    # The v0-Doppler / probe-Stark compiler-fix params are inherited from
    # DeclarativeLMTCoreBase and exposed on every RoiCheck frag.
    assert hasattr(frag, "lmt_initial_velocity")
    assert hasattr(frag, "lmt_probe_stark_alpha")

    # The dynamic-ROI predictor result channels are present (predictor under
    # test is the production NormalisedFastKineticsLMTCorrectedMixin one).
    for channel in (
        "predicted_gnd_x",
        "predicted_gnd_y",
        "predicted_excited_x",
        "predicted_excited_y",
    ):
        assert hasattr(frag, channel)

    # The compiled sequence was attached at build time.
    assert hasattr(frag, "_lmt_compiled")


def test_scan_exps_are_module_globals():
    # Both the Frag and the scan-exp must be module globals so ARTIQ can find
    # them in the explist.
    for name in (
        "RoiCheckFall",
        "RoiCheckUp",
        "RoiCheckDown",
        "RoiCheckFallExp",
        "RoiCheckUpExp",
        "RoiCheckDownExp",
        "RoiCheckUp2Sliced",
        "RoiCheckUp2SlicedExp",
        "RoiCheckSlicedBaseline",
        "RoiCheckSlicedBaselineExp",
        "RoiCheckSlicedLaunch1",
        "RoiCheckSlicedLaunch1Exp",
        "RoiCheckSlicedLaunch2",
        "RoiCheckSlicedLaunch2Exp",
        "RoiCheckSlicedLaunch3",
        "RoiCheckSlicedLaunch3Exp",
    ):
        assert hasattr(rpc, name), name
