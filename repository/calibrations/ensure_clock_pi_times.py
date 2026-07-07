"""
Client for the full clock-calibration DAG: XODT -> Cal1 (delivery) ->
{Cal2 up-pi, Cal3 down-pi}. Pulling both Rabi calibrations dedups the shared
ClockDeliveryAOMCalibration node, so one run walks the whole DAG and publishes
all three nodes to calibrations.dag / calibrations.status (rendered by the DAG
applet).
"""


from repository.lib.utils import _Stub


class EnsureClockPiTimes(_Stub):
    """
    Client for the full clock-calibration DAG: XODT -> Cal1 (delivery) ->
    {Cal2 up-pi, Cal3 down-pi}. Pulling both Rabi calibrations dedups the shared
    ClockDeliveryAOMCalibration node, so one run walks the whole DAG and publishes
    all three nodes to calibrations.dag / calibrations.status (rendered by the DAG
    applet).
    """
