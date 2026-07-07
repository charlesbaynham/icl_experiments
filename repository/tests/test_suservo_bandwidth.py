"""AUTO-GENERATED stub file - do not edit by hand.

Regenerate with ``scripts/generate_stubs.py``. Every class here mirrors
the name and docstring of a real experiment on a source branch; the
body is a no-op stub so the ARTIQ explorer can list it without any of
the real dependencies.
"""

from repository.stub_experiment import _Stub


class DetermineServoPeriod(_Stub):
    """
    Determine servo period

    This determines the length of a cycle on the given SUServo device by
    repeatedly fetching the status word and recording timestamps where the
    "done" bit is set (which is strobed for one clock cycle at the end of
    each cycle).
    """
