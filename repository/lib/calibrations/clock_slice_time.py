"""
Slice-time consumer contract for the clock Rabi calibrations.

Downstream true experiments must NOT keep using the nominal slice time once the
Rabi calibrations have produced measured pi times. The slice and the short pulses
share the beam/intensity anchor, so the slice time scales with the pi time::

    T_slice_true = T_slice_nominal * (T_pi_measured / T_pi_nominal)

This mirrors the AC-Stark grid's ``V_auto = V_ref*(T_ref/T)**2`` anchor logic. The
measured pi time is read from the qbutler-persisted dataset (``constants.py`` holds
the fallback default when the dataset is absent) -- never from the constant
directly, so a recalibration propagates.
"""


from repository.lib.utils import _Stub


class ClockSliceTimeConsumer(_Stub):
    """
    Demonstrator: derive the true slice time from the persisted pi times.

    Reads each beam's calibrated pi time from its qbutler dataset (falling back to
    the constant when absent) and computes the scaled slice time -- the value a
    true experiment must use instead of the nominal ``CLOCK_SHELVING_PULSE_TIME``.
    """
