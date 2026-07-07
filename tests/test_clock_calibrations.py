"""Host-side test for the slice-time consumer contract. Calibration fragment
build/compile is covered separately by test_calibration_kernels."""

import numpy as np


def test_scaled_clock_slice_time_ratio():
    from repository.lib import constants
    from repository.lib.calibrations.clock_slice_time import scaled_clock_slice_time
    from repository.lib.lmt_sequence import Beam

    # A pi time equal to nominal leaves the slice time unchanged
    for beam, nominal in (
        (Beam.UP, constants.CLOCK_PI_TIME),
        (Beam.DOWN, constants.DOWN_CLOCK_BEAM_PI_TIME),
    ):
        assert np.isclose(
            scaled_clock_slice_time(nominal, beam), constants.CLOCK_SHELVING_PULSE_TIME
        )
        # A 10% longer pi time scales the slice by 10%
        assert np.isclose(
            scaled_clock_slice_time(1.1 * nominal, beam),
            1.1 * constants.CLOCK_SHELVING_PULSE_TIME,
        )
