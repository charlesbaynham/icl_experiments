"""AUTO-GENERATED stub file - do not edit by hand.

Regenerate with ``scripts/generate_stubs.py``. Every class here mirrors
the name and docstring of a real experiment on a source branch; the
body is a no-op stub so the ARTIQ explorer can list it without any of
the real dependencies.
"""

from repository.stub_experiment import _Stub


class Steer641StartPiezoScan(_Stub):
    """
    Steer the 641nm laser to a target detuning via WAND, disable WAND locking,
    then run a piezo scan on the Toptica DLCPro indefinitely. The laser is
    periodically re-steered to correct for drift. The scan is disabled on exit.
    """
