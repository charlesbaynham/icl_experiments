"""AUTO-GENERATED stub file - do not edit by hand.

Regenerate with ``scripts/generate_stubs.py``. Every class here mirrors
the name and docstring of a real experiment on a source branch; the
body is a no-op stub so the ARTIQ explorer can list it without any of
the real dependencies.
"""

from repository.stub_experiment import _Stub


class ClockSpecPulseRatio(_Stub):
    """
    Clock spectroscopy from dropped single XODT with OPLL-based gravity compensation
    and auto-scaled clock delivery setpoint.

    Selection pulse duration = clock pulse duration * pulse_ratio.
    Clock delivery setpoint auto-calculated: V = V_ref * (T_ref / T_clock)^2.
    OPLL exclusively controls clock frequency; switch DDSes are constant.
    """
