"""THROWAWAY spike: confirm removing/throttling the gc.collect collapses build time."""
import gc, time
import qbutler.dag as dag
from repository.calibrations.ensure_clock_pi_times import EnsureClockPiTimesFrag


def _time_build(factory):
    t0 = time.perf_counter()
    factory(EnsureClockPiTimesFrag)
    return time.perf_counter() - t0


def test_spike(fragment_factory):
    held = [[{"a":[1,2,3],"b":(4,5)} for _ in range(6_000_000)]]  # big heap ~ master-like
    n_obj = len(gc.get_objects())
    print("\nHeap objects: %d" % n_obj)

    # 1) BASELINE (unpatched)
    print("BASELINE (gc.collect per add_dependency): %.2f s" % _time_build(fragment_factory))

    # 2) SPIKE A: remove gc.collect from _filter_dependency_map entirely
    orig_collect = dag.gc.collect
    dag.gc.collect = lambda *a, **k: 0
    try:
        print("SPIKE A (no gc.collect in filter):        %.2f s" % _time_build(fragment_factory))
    finally:
        dag.gc.collect = orig_collect

    # 3) SPIKE B: young-generation-only collect (gen 0) instead of full gen-2
    dag.gc.collect = lambda *a, **k: orig_collect(0)
    try:
        print("SPIKE B (gc.collect(0) young-gen only):   %.2f s" % _time_build(fragment_factory))
    finally:
        dag.gc.collect = orig_collect
