"""AUTO-GENERATED stub file - do not edit by hand.

Regenerate with ``scripts/generate_stubs.py``. Every class here mirrors
the name and docstring of a real experiment on a source branch; the
body is a no-op stub so the ARTIQ explorer can list it without any of
the real dependencies.
"""

from repository.stub_experiment import _Stub


class ClockSliceTimeConsumer(_Stub):
    """
    Demonstrator: derive the true slice time from the persisted pi times.

    Reads each beam's calibrated pi time from its qbutler dataset (falling back to
    the constant when absent) and computes the scaled slice time -- the value a
    true experiment must use instead of the nominal ``CLOCK_SHELVING_PULSE_TIME``.
    """
