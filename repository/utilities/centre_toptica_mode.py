"""AUTO-GENERATED stub file - do not edit by hand.

Regenerate with ``scripts/generate_stubs.py``. Every class here mirrors
the name and docstring of a real experiment on a source branch; the
body is a no-op stub so the ARTIQ explorer can list it without any of
the real dependencies.
"""

from repository.stub_experiment import _Stub


class CentreAllTopticaModes(_Stub):
    """
    Centre all Toptica laser modes within their mode-hop free ranges.

    This experiment iterates through all Toptica lasers defined in
    TOPTICA_TO_WAND_NAMES and centres each one by creating a subfragment
    for each laser and running the centring algorithm.
    """


class CentreTopticaMode(_Stub):
    """
    Centre a Toptica laser mode within its mode-hop free range.

    This experiment centres the mode of a Toptica laser so that it is at a
    specified position within its mode-hop free range. The laser must already
    be lasing on the correct mode before running this experiment.

    Algorithm:
        -1. Disable ARC if enabled to prevent external steering
        0. Confirm that the laser is on the correct mode (within 15 GHz of setpoint)
        1. Record the starting voltage and current
        2. Turn off feed-forward
        3. Increase current until mode hop occurs
        4. Record the current just before the mode-hop as I_top
        5. Jump back to starting position and restore lasing on the correct mode
           if necessary by jumping current down and back up
        6. Decrease current until mode hop occurs
        7. Record the current just before the mode-hop as I_bottom
        8. Calculate the target current based on mode_position_fraction parameter
        9. Jump to this current and restore lasing on the correct mode if necessary
        10. Turn on feed-forward if it was originally enabled
        11. Steer the wavelength to the frequency setpoint using WAND
        12. Check the current drift. If too large, iterate from step 1
        13. Re-enable ARC if it was originally enabled
    """
