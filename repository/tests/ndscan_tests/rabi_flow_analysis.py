"""AUTO-GENERATED stub file - do not edit by hand.

Regenerate with ``scripts/generate_stubs.py``. Every class here mirrors
the name and docstring of a real experiment on a source branch; the
body is a no-op stub so the ARTIQ explorer can list it without any of
the real dependencies.
"""

from repository.stub_experiment import _Stub


class PiTimeFitSimScan(_Stub):
    pass


class RabiFlopWithAnalysisScan(_Stub):
    """
    Rabi flop example, extended by a custom default analysis and fit procedure

    (Usually, get_default_analyses() would directly be defined in the respective
    ExpFragment; we just extend RabiFlopSim here to avoid code duplication while keeping
    the other example simple.)
    """
