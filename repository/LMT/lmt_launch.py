"""AUTO-GENERATED stub file - do not edit by hand.

Regenerate with ``scripts/generate_stubs.py``. Every class here mirrors
the name and docstring of a real experiment on a source branch; the
body is a no-op stub so the ARTIQ explorer can list it without any of
the real dependencies.
"""

from repository.stub_experiment import _Stub


class DoubleLaunchFromXODT(_Stub):
    """
    Double launch from XODT

    Load into an XODT, shelve with a Jesse pulse, then use LMT for launching

    Image the ground state atoms, repump and image the excited state, then image
    once more for background.
    """


class LaunchFromXODT(_Stub):
    """
    Launch from XODT

    Load into an XODT, then use LMT for launching

    Image the ground state atoms, repump and image the excited state, then image
    once more for background.
    """


class LaunchFromXODTShapedShelving(_Stub):
    """
    Launch from XODT with shaped shelving

    Load into an XODT, shelve with a Jesse pulse, then use LMT for launching

    Image the ground state atoms, repump and image the excited state, then image
    once more for background.
    """
