"""Slice-time consumer contract for the clock Rabi calibrations.

Downstream true experiments must NOT keep using the nominal slice time once the
Rabi calibrations have produced measured pi times. The slice and the short pulses
share the beam/intensity anchor, so the slice time scales with the pi time::

    T_slice_true = T_slice_nominal * (T_pi_measured / T_pi_nominal)

This mirrors the AC-Stark grid's ``V_auto = V_ref*(T_ref/T)**2`` anchor logic. The
measured pi time is read from the qbutler-persisted dataset (``constants.py`` holds
the fallback default when the dataset is absent) -- never from the constant
directly, so a recalibration propagates.
"""

import logging
import time

from ndscan.experiment import ExpFragment
from ndscan.experiment.entry_point import make_fragment_scan_exp

from repository.lib import constants
from repository.lib.lmt_sequence import Beam

logger = logging.getLogger(__name__)

#: Idle wait per iteration so a "run forever" repeat throttles instead of
#: re-reading the datasets back-to-back.
IDLE_SLEEP_S = 30.0

_NOMINAL_PI_TIME = {
    Beam.UP: constants.CLOCK_PI_TIME,
    Beam.DOWN: constants.DOWN_CLOCK_BEAM_PI_TIME,
}
_PI_DATASET = {
    Beam.UP: "calibrations.RabiUpPiTimeCalibration.pi_time",
    Beam.DOWN: "calibrations.RabiDownPiTimeCalibration.pi_time",
}


def scaled_clock_slice_time(measured_pi_time, beam):
    """Slice time scaled from its nominal by the measured/nominal pi-time ratio."""
    return (
        constants.CLOCK_SHELVING_PULSE_TIME * measured_pi_time / _NOMINAL_PI_TIME[beam]
    )


class ClockSliceTimeConsumerFrag(ExpFragment):
    """Demonstrator: derive the true slice time from the persisted pi times.

    Reads each beam's calibrated pi time from its qbutler dataset (falling back to
    the constant when absent) and computes the scaled slice time -- the value a
    true experiment must use instead of the nominal ``CLOCK_SHELVING_PULSE_TIME``.
    """

    def build_fragment(self):
        pass

    def run_once(self):
        for beam in (Beam.UP, Beam.DOWN):
            measured_pi = self.get_dataset(
                _PI_DATASET[beam], default=_NOMINAL_PI_TIME[beam]
            )
            slice_time = scaled_clock_slice_time(measured_pi, beam)
            logger.info(
                "%s: pi=%.2f us (nominal %.2f) -> slice=%.2f us (nominal %.2f)",
                beam,
                1e6 * measured_pi,
                1e6 * _NOMINAL_PI_TIME[beam],
                1e6 * slice_time,
                1e6 * constants.CLOCK_SHELVING_PULSE_TIME,
            )

        time.sleep(IDLE_SLEEP_S)


ClockSliceTimeConsumer = make_fragment_scan_exp(ClockSliceTimeConsumerFrag)
