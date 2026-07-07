"""AUTO-GENERATED stub file - do not edit by hand.

Regenerate with ``scripts/generate_stubs.py``. Every class here mirrors
the name and docstring of a real experiment on a source branch; the
body is a no-op stub so the ARTIQ explorer can list it without any of
the real dependencies.
"""

from repository.stub_experiment import _Stub


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
