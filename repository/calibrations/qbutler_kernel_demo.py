"""AUTO-GENERATED stub file - do not edit by hand.

Regenerate with ``scripts/generate_stubs.py``. Every class here mirrors
the name and docstring of a real experiment on a source branch; the
body is a no-op stub so the ARTIQ explorer can list it without any of
the real dependencies.
"""

from repository.stub_experiment import _Stub


class QbutlerKernelDemo(_Stub):
    """
    Demonstrate qbutler Calibrations running kernel functions on the real Kasli.

    Two demos:
    - ``KernelDemoCalibration``: ``@kernel check_own_state`` — compiles, owns the
      timeline, returns ``(CalibrationResult, float)`` through the RPC boundary.
    - ``KernelFixDemoCalibration``: host check that fails until the ``@kernel``
      ``fix_own_state`` has run (device-side repair demo).
    """
