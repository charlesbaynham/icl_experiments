"""AUTO-GENERATED stub file - do not edit by hand.

Regenerate with ``scripts/generate_stubs.py``. Every class here mirrors
the name and docstring of a real experiment on a source branch; the
body is a no-op stub so the ARTIQ explorer can list it without any of
the real dependencies.
"""

from repository.stub_experiment import _Stub


class EnsureClockPiTimes(_Stub):
    """
    Client for the full clock-calibration DAG: XODT -> Cal1 (delivery) ->
    {Cal2 up-pi, Cal3 down-pi}. Pulling both Rabi calibrations dedups the shared
    ClockDeliveryAOMCalibration node, so one run walks the whole DAG and publishes
    all three nodes to calibrations.dag / calibrations.status (rendered by the DAG
    applet).
    """
