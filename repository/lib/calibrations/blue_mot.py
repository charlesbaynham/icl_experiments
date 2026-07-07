from repository.lib.utils import _Stub


class BlueMOTCalibrationExp(_Stub):
    """
    The blue MOT loads well; optimizes the push-beam SUServo setpoint.

    Metric: background-corrected vertical FLIR fluorescence after a normal
    MOT load. The threshold parameter defaults (via dataset) to an impossibly
    high value so the calibration fails closed until it has been set from
    live data.
    """
