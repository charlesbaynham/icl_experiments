from repository.lib.utils import _Stub


class RedMOTCalibrationExp(_Stub):
    """
    The narrowband red MOT loads well; optimizes 689 AOM frequency and
    narrowband bias fields.

    Depends on :class:`BlueMOTCalibration` — a red MOT needs a healthy blue
    MOT to load from, and this calibration feeds the blue-optimized push
    setpoint into its own loading stage.

    Metric: background-corrected Andor fluorescence sum of the in-situ
    narrowband MOT (no dipole trap needed). Four optimizable parameters, so
    the optimizer is a coordinate descent (7 points/axis, 2 rounds = 56
    shots) rather than a grid.
    """
