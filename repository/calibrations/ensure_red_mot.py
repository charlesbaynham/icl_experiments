"""
Client experiment that *uses* the red-MOT calibration.

Running this proves the qbutler DAG contract: the whole chain (blue MOT →
red MOT) is checked, and anything BAD/expired is re-optimized, before the
client proceeds. Within the check-state timeout a re-submission does nothing
at all (state is recalled from the calibrations.status dataset).
"""


from repository.lib.utils import _Stub


class EnsureRedMOT(_Stub):
    """
    Client experiment that *uses* the red-MOT calibration.

    Running this proves the qbutler DAG contract: the whole chain (blue MOT →
    red MOT) is checked, and anything BAD/expired is re-optimized, before the
    client proceeds. Within the check-state timeout a re-submission does nothing
    at all (state is recalled from the calibrations.status dataset).
    """
