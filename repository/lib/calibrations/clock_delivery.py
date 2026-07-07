from repository.lib.utils import _Stub


class ClockDeliveryAOMCalibrationExp(_Stub):
    """
    Centre the shared clock ``clock_delivery`` SUServo delivery AOM frequency.

    The delivery AOM is common to the up and down clock beams (split by the OPLL
    offset), so its frequency is the common-mode centring knob.
    :class:`NarrowDownAfterSliceFrag` velocity-slices with a narrow (~1.3 kHz)
    up-slice -- which gives the sharp centring sensitivity -- then de-shelves with
    a NORMAL-power down pulse (overridden below) so the whole shelved class is
    recovered and imaged with the dual-image re-pumped readout: healthy atoms and
    a sharp, high-SNR peak in the shelved fraction versus delivery frequency.

    Optimizable parameter: the ``frequency_clock_delivery`` SUServo delivery
    frequency (persisted to dataset
    ``calibrations.ClockDeliveryAOMCalibration.delivery_frequency``; ``constants.py``
    holds the fallback default).
    """
