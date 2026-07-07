"""AUTO-GENERATED stub file - do not edit by hand.

Regenerate with ``scripts/generate_stubs.py``. Every class here mirrors
the name and docstring of a real experiment on a source branch; the
body is a no-op stub so the ARTIQ explorer can list it without any of
the real dependencies.
"""

from repository.stub_experiment import _Stub


class Relock1379Cavity(_Stub):
    """
    Relock the 1379  to the doubled 689 PLL

    Change the WAND exposures before doing the relock, but be sure to change
    them back afterwards
    """


class Relock689Cavity(_Stub):
    """
    Relock the 689 master to the laser stabilization cavity

    To do this, we must handle the shutters for the 689 & 1379 wavemeter
    multiplexing. This will involve blocking the 1379 light, unlocking its PLL.
    So this will need to be relocked next: see :class:`~.Relock1379Frag`.
    """


class Relock698Cavity(_Stub):
    """
    Relock the 698 to the laser stabilization cavity

    For the 698, this is straightforward
    """


class SetShutters689(_Stub):
    """
    Manually set the 689 and 1379 wavemeter shutters
    """
