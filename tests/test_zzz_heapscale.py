"""THROWAWAY: does EnsureClockPiTimes build time scale with pre-existing heap size?"""
import gc, time
from repository.calibrations.ensure_clock_pi_times import EnsureClockPiTimesFrag


def _build_time(factory):
    import qbutler.dag as dag
    n_collect = {"n": 0, "t": 0.0}
    orig = dag.gc.collect
    def counted(*a, **k):
        t0 = time.perf_counter(); r = orig(*a, **k); n_collect["t"] += time.perf_counter()-t0; n_collect["n"] += 1; return r
    dag.gc.collect = counted
    try:
        t0 = time.perf_counter()
        factory(EnsureClockPiTimesFrag)
        wall = time.perf_counter() - t0
    finally:
        dag.gc.collect = orig
    return wall, n_collect["n"], n_collect["t"]


def test_heapscale(fragment_factory):
    held = []
    for label, add in [("clean", 0), ("+1M", 1_000_000), ("+3M", 3_000_000), ("+6M", 6_000_000)]:
        if add:
            held.append([{"a":[1,2,3],"b":(4,5)} for _ in range(add)])
        n_obj = len(gc.get_objects())
        wall, ncol, tcol = _build_time(fragment_factory)
        print("HEAP %-6s objects=%9d  BUILD=%6.2f s  gc.collect: n=%d total=%5.2f s (%.0f%% of build)"
              % (label, n_obj, wall, ncol, tcol, 100*tcol/wall))
