"""AUTO-GENERATED stub file - do not edit by hand.

Regenerate with ``scripts/generate_stubs.py``. Every class here mirrors
the name and docstring of a real experiment on a source branch; the
body is a no-op stub so the ARTIQ explorer can list it without any of
the real dependencies.
"""

from repository.stub_experiment import _Stub


class MeasureCooledXODT(_Stub):
    """
    Measure a Single XODT with adiabatic cooling and delta kick
    """


class MeasureSingleXODTAbs(_Stub):
    """
    Measure a single XODT with absorption imaging
    """


class MeasureSingleXODTBGCorrected(_Stub):
    """
    Make Single XODT and image twice for BG subtraction
    """


class SingleXODTHorizontalYSloshed(_Stub):
    """
    Horizontally slosh a single XODT

    Load an XODT, use evaporation ramps to keep the coldest atoms and to ramp back up
    to desired trap depth, then use a spinpol beam to displace the atoms horizontally
    """


class SingleXODTSloshed(_Stub):
    """
    Slosh a single XODT

    Make Single XODT, hold it for some time, turn off the vertical trap, let it
    slosh then image
    """


class SingleXODTVerticalSloshed(_Stub):
    """
    Vertically slosh a single XODT

    Make Single XODT, decrease HODT depth to displace the atoms under gravity,
    switch up the HODT depth and let it slosh, then drop and image
    """
