"""AUTO-GENERATED stub file - do not edit by hand.

Regenerate with ``scripts/generate_stubs.py``. Every class here mirrors
the name and docstring of a real experiment on a source branch; the
body is a no-op stub so the ARTIQ explorer can list it without any of
the real dependencies.
"""

from repository.stub_experiment import _Stub


class BlueMOTCalibrationExp(_Stub):
    """
    The blue MOT loads well; optimizes the push-beam SUServo setpoint.

    Metric: background-corrected vertical FLIR fluorescence after a normal
    MOT load. The threshold parameter defaults (via dataset) to an impossibly
    high value so the calibration fails closed until it has been set from
    live data.
    """
