"""
Top-level client for the whole blue-MOT-to-clock calibration chain.

Running this proves the connected qbutler DAG contract end to end: fixing the
refined clock-centre node walks the whole chain furthest-first
(blue MOT -> red MOT -> coarse clock centre -> refined clock centre),
re-measuring only stale nodes, before the client proceeds. Within every node's
timeout a re-submission does nothing at all (state recalled from the
calibrations.status dataset).
"""


from repository.lib.utils import _Stub


class EnsureClockCentre(_Stub):
    """
    Top-level client for the whole blue-MOT-to-clock calibration chain.

    Running this proves the connected qbutler DAG contract end to end: fixing the
    refined clock-centre node walks the whole chain furthest-first
    (blue MOT -> red MOT -> coarse clock centre -> refined clock centre),
    re-measuring only stale nodes, before the client proceeds. Within every node's
    timeout a re-submission does nothing at all (state recalled from the
    calibrations.status dataset).
    """
