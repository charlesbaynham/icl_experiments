"""AUTO-GENERATED stub file - do not edit by hand.

Regenerate with ``scripts/generate_stubs.py``. Every class here mirrors
the name and docstring of a real experiment on a source branch; the
body is a no-op stub so the ARTIQ explorer can list it without any of
the real dependencies.
"""

from repository.stub_experiment import _Stub


class ResetAllUrukuls(_Stub):
    """
    Reset all Urukuls' AD991x devices

    Sometimes the AD9910s and AD9912s get stuck in a bad state, most often if
    you delete an experiment while its running. This experiment will attempt to
    save them by pulsing MASTER_RESET on *every* Urukul connected to the system.
    User beware.
    """
