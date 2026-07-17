"""THROWAWAY profiling harness for the lazy-builds scoping pass. Not for merge."""
import cProfile
import io
import pstats
import time

from repository.calibrations.ensure_clock_pi_times import EnsureClockPiTimesFrag
from repository.LMT.lmt_clock_ratio_calibration import DeclarativeClockRatioCalUpFrag


def _profile_build(factory, cls, label):
    import repository.lib.experiment_templates.mixins.declarative_lmt as dl
    calls = {"n": 0, "t": 0.0, "events": 0}
    orig = dl.compile_sequence

    def wrapped(events, **kw):
        t0 = time.perf_counter()
        r = orig(events, **kw)
        calls["t"] += time.perf_counter() - t0
        calls["n"] += 1
        calls["events"] += len(r.events)
        return r

    dl.compile_sequence = wrapped
    try:
        pr = cProfile.Profile()
        t0 = time.perf_counter()
        pr.enable()
        frag = factory(cls)
        pr.disable()
        wall = time.perf_counter() - t0
    finally:
        dl.compile_sequence = orig

    s = io.StringIO()
    ps = pstats.Stats(pr, stream=s).sort_stats("cumulative")
    ps.print_stats(45)
    print("\n\n========== %s ==========" % label)
    print("WALL build+init_params: %.3f s" % wall)
    print("compile_sequence: n=%d total_events=%d cumulative_time=%.1f ms"
          % (calls["n"], calls["events"], calls["t"] * 1000))
    print(s.getvalue())
    s2 = io.StringIO()
    ps2 = pstats.Stats(pr, stream=s2).sort_stats("tottime")
    ps2.print_stats(30)
    print("---- by tottime ----")
    print(s2.getvalue())


def test_profile_single_ratio_cal(fragment_factory):
    _profile_build(fragment_factory, DeclarativeClockRatioCalUpFrag, "SINGLE DeclarativeClockRatioCalUpFrag")


def test_profile_ensure_pi_times(fragment_factory):
    _profile_build(fragment_factory, EnsureClockPiTimesFrag, "EnsureClockPiTimesFrag (2 chains)")
