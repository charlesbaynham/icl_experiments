"""THROWAWAY: is the PARAMS schema affected by the gc.collect removal, controlling
for build-twice-in-one-process global-state noise?"""
import json, difflib
import qbutler.dag as dag
from repository.calibrations.ensure_clock_pi_times import EnsureClockPiTimesFrag


def _schema(factory):
    frag = factory(EnsureClockPiTimesFrag)
    params, schemata, samples = {}, {}, {}
    frag._collect_params(params, schemata, samples)
    return json.dumps({"params": params, "schemata": schemata}, sort_keys=True, indent=1, default=str)


def _diff(a, b, tag):
    d = list(difflib.unified_diff(a.splitlines(), b.splitlines(), lineterm="", n=0))
    print("\n[%s] identical=%s  diff_lines=%d" % (tag, a == b, len(d)))
    for line in d[:40]:
        print("   ", line)


def test_arginfo(fragment_factory):
    # CONTROL: two builds, both with gc.collect ON
    a = _schema(fragment_factory)
    b = _schema(fragment_factory)
    _diff(a, b, "CONTROL gcON vs gcON (build-twice noise)")

    # TREATMENT: next build with gc.collect OFF
    orig = dag.gc.collect
    dag.gc.collect = lambda *x, **k: 0
    try:
        c = _schema(fragment_factory)
    finally:
        dag.gc.collect = orig
    _diff(b, c, "TREATMENT gcON vs gcOFF")
