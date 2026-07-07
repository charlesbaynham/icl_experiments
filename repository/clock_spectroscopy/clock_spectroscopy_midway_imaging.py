"""AUTO-GENERATED stub file - do not edit by hand.

Regenerate with ``scripts/generate_stubs.py``. Every class here mirrors
the name and docstring of a real experiment on a source branch; the
body is a no-op stub so the ARTIQ explorer can list it without any of
the real dependencies.
"""

from repository.stub_experiment import _Stub


class ClockSpecMidwayImaging(_Stub):
    """
    Midway imaging of clock sequence

    Load into an XXODT, spin-polarize the atoms then velocity slice them, as if
    for a clock interferometry / spec experiment.

    But, image midway through the sequence instead, with the imaging time
    measured relative to the start of the BB red MOT.

    Finally, take a background image at the end of the sequence.
    """
