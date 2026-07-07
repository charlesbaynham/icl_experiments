"""
Clock Rabi / set-point ratio calibration in the declarative LMT framework.

Re-measures the post-rebuild Rabi anchor ``(V_ref, T_ref)`` per beam: a fixed
velocity-selective slice + clearout prepares a clean velocity class, then a
single probe pulse on the *same beam* drives it coherently. Scanning the probe
duration gives a Rabi flop whose pi time is the new ``T_ref`` at the operating
delivery set point ``V_ref``. The slice and probe share a beam (and therefore a
Doppler class), unlike the normal declarative LMT sequence which slices up and
launches down.

Readout is re-pumped (parameter-independent), so the flop is imaged without a
clock pulse whose frequency would itself depend on the delivery calibration. The
qbutler ``RabiUp/DownPiTimeCalibration`` wrap these fragments and persist the
fitted pi time to a dataset (``constants.py`` holds the fallback default); the
clock AC-Stark retake (``DeclarativeClockShift{Up,Down}``) and any slice-time
consumer read that dataset.
"""


from repository.lib.utils import _Stub


class DeclarativeClockRatioCalUp(_Stub):
    """
    Up-beam clock Rabi/set-point ratio calibration.
    """


class DeclarativeClockRatioCalDown(_Stub):
    """
    Down-beam clock Rabi/set-point ratio calibration.
    """
