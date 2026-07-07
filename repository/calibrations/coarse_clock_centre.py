"""AUTO-GENERATED stub file - do not edit by hand.

Regenerate with ``scripts/generate_stubs.py``. Every class here mirrors
the name and docstring of a real experiment on a source branch; the
body is a no-op stub so the ARTIQ explorer can list it without any of
the real dependencies.
"""

from repository.stub_experiment import _Stub


class CoarseClockCentreCalibrationExp(_Stub):
    """
    Coarsely centre the shared clock ``clock_delivery`` SUServo delivery AOM.

    A single full-power clock pi on the trapped ground cloud gives a broad,
    power-broadened excitation feature versus delivery frequency. This node
    finds its middle over a wide window and persists it as the seed the
    :class:`~repository.lib.calibrations.clock_delivery.ClockDeliveryAOMCalibration`
    (refined) node recentres its narrow window on.

    Depends on :class:`RedMOTCalibration` - a healthy MOT is needed to load the
    XODT the clock pulse addresses - so the whole blue -> red -> coarse -> refined
    chain is one connected DAG.

    Optimizable parameter: the ``frequency_clock_delivery`` SUServo delivery
    frequency (persisted to dataset
    ``CoarseClockCentreCalibration.delivery_frequency``; ``constants.py`` holds
    the fallback default).
    """
