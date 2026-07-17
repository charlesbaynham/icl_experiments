"""THROWAWAY: interim fix F3 = full gc.collect at most ONCE per top-level build.
Prove (a) under 15s at master-like heap, (b) arginfo byte-identical to baseline."""
import gc, json, time
import qbutler.dag as dag
from repository.calibrations.ensure_clock_pi_times import EnsureClockPiTimesFrag

_build_gen = {"n": 0, "last_collect_gen": -1}
_real_collect = gc.collect

def _throttled_collect(*a, **k):
    # Only actually collect the first time within a given build generation.
    if _build_gen["last_collect_gen"] != _build_gen["n"]:
        _build_gen["last_collect_gen"] = _build_gen["n"]
        return _real_collect()
    return 0

def _schema(factory):
    frag = factory(EnsureClockPiTimesFrag)
    params, schemata, samples = {}, {}, {}
    frag._collect_params(params, schemata, samples)
    return json.dumps({"params": params, "schemata": schemata}, sort_keys=True, default=str)

def test_f3(fragment_factory):
    held = [[{"a":[1,2,3],"b":(4,5)} for _ in range(6_000_000)]]
    print("\nHeap objects:", len(gc.get_objects()))

    # Baseline schema + time (unpatched, gc per add_dependency)
    t0 = time.perf_counter(); base = _schema(fragment_factory); t_base = time.perf_counter()-t0
    print("BASELINE build %.2fs" % t_base)

    # Patch: throttle to once per build
    dag.gc.collect = _throttled_collect
    try:
        for i in range(3):  # several sequential builds sharing the process (examine-worker-like)
            _build_gen["n"] += 1
            t0 = time.perf_counter(); s = _schema(fragment_factory); dt = time.perf_counter()-t0
            print("F3 build #%d  %.2fs  arginfo==baseline: %s" % (i+1, dt, s == base))
    finally:
        dag.gc.collect = _real_collect
