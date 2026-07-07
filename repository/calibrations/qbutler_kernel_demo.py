"""
Demonstrate qbutler Calibrations running kernel functions on the real Kasli.

Two demos:
- ``KernelDemoCalibration``: ``@kernel check_own_state`` — compiles, owns the
  timeline, returns ``(CalibrationResult, float)`` through the RPC boundary.
- ``KernelFixDemoCalibration``: host check that fails until the ``@kernel``
  ``fix_own_state`` has run (device-side repair demo).
"""


from repository.lib.utils import _Stub


class QbutlerKernelDemo(_Stub):
    """
    Demonstrate qbutler Calibrations running kernel functions on the real Kasli.

    Two demos:
    - ``KernelDemoCalibration``: ``@kernel check_own_state`` — compiles, owns the
      timeline, returns ``(CalibrationResult, float)`` through the RPC boundary.
    - ``KernelFixDemoCalibration``: host check that fails until the ``@kernel``
      ``fix_own_state`` has run (device-side repair demo).
    """
