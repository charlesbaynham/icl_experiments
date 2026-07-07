"""AUTO-GENERATED stub file - do not edit by hand.

Regenerate with ``scripts/generate_stubs.py``. Every class here mirrors
the name and docstring of a real experiment on a source branch; the
body is a no-op stub so the ARTIQ explorer can list it without any of
the real dependencies.
"""

from repository.stub_experiment import _Stub


class MeasureXXODT(_Stub):
    """
    Measure a double XODT

    Load a red MOT on the top XODT, drop the bias field to centre the MOT on the
    second XODT then turn the light back on.
    """


class MeasureXXODTAbsorption(_Stub):
    """
    Measure a double XODT with absorption imaging
    """


class MeasureXXODTWithTransparency(_Stub):
    """
    Measure a double XODT with transparency beam
    """


class StarkBlastXXODT(_Stub):
    """
    Blast an XXODT with the Stark shifter

    In the "evaporation" stage, the 689 nm Stark beam is pulsed on to destroy atoms
    (for alignment of the beam onto the XODT). Note: this will only work the
    0th order of the 689 delivery AOM is coupled to the chamber - otherwise the
    beam will be ~ 100 MHz from resonance.
    """
