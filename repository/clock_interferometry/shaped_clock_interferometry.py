"""AUTO-GENERATED stub file - do not edit by hand.

Regenerate with ``scripts/generate_stubs.py``. Every class here mirrors
the name and docstring of a real experiment on a source branch; the
body is a no-op stub so the ARTIQ explorer can list it without any of
the real dependencies.
"""

from repository.stub_experiment import _Stub


class ClockInterferometryFromSingleXODTEvaporatedShapedSlicing(_Stub):
    """
    Clock interferometry from dropped single XODT with evaporation, shaped shelving and clearout

    Load into an XODT, velocity-slice using a shaped pulse, then use the up clock beam for spectroscopy, altering the
    (single-pass) AOM.

    Image the ground state atoms, repump and image the excited state, then image
    once more for background.
    """
