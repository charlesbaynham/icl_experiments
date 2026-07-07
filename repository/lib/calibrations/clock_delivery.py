import logging

import numpy as np
from artiq.coredevice.core import Core
from artiq.experiment import kernel
from ndscan.experiment.entry_point import make_fragment_scan_exp
from ndscan.experiment.parameters import FloatParam
from ndscan.experiment.parameters import IntParam
from ndscan.experiment.parameters import FloatParamHandle
from ndscan.experiment.parameters import IntParamHandle
from ndscan.experiment.result_channels import LastValueSink

from qbutler.calibration import Calibration
from qbutler.calibration import CalibrationResult
from repository.lib.calibrations._fit_helpers import fit_peak_x
from repository.lib import constants
from repository.LMT_declarative.lmt_tune_slice import NarrowDownAfterSliceFrag
from repository.lib.calibrations.coarse_clock_centre import (
    CoarseClockCentreCalibration,
)

logger = logging.getLogger(__name__)

_CLOCK_DELIVERY_INFO = constants.SUSERVOED_BEAMS["clock_delivery"]
_NOMINAL_DELIVERY_FREQUENCY = _CLOCK_DELIVERY_INFO.frequency

#: Half-width of the delivery-frequency search window, recentred on the coarse
#: seed (see build_calibration). A precision window, not an acquisition one: the
#: coarse node has already found the line to within a few kHz, and the narrow
#: down_spec pulse is Fourier-narrow (~1 kHz), refined to sub-grid precision by
#: the parabolic fit.
_SEARCH_HALF_SPAN = 30e3

#: Dataset the coarse line-finder persists its fitted centre to; the refined
#: window recentres on it, falling back to nominal when the coarse node has
#: never run.
_COARSE_SEED_DATASET = f"{CoarseClockCentreCalibration.__name__}.delivery_frequency"

#: Points in one delivery-frequency sweep during a fix (+/-30 kHz over 61 points
#: = 1 kHz grid, refined to sub-grid precision by the parabolic peak fit below).
_SWEEP_POINTS = 61


def _delivery_fit_optimizer(param_specs):
    """qbutler optimizer generator: sweep the delivery frequency once across the
    search window, then return the parabolic-fitted line centre as the best
    param. Reuses the framework persist + re-verify path in _run_optimizer_host.
    """
    (spec,) = param_specs
    freqs = np.linspace(spec.min, spec.max, _SWEEP_POINTS)

    excitations = []
    for f in freqs:
        _, data = yield {spec.name: float(f)}
        excitations.append(data if isinstance(data, (int, float)) else np.nan)

    centre = fit_peak_x(freqs, excitations)
    if centre is None:
        return None
    return {spec.name: float(centre)}


class ClockDeliveryAOMCalibration(Calibration):
    """Centre the shared clock ``clock_delivery`` SUServo delivery AOM frequency.

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

    def build_calibration(self):
        self.setattr_device("core")
        self.core: Core

        self.add_dependency(CoarseClockCentreCalibration)
        self.CoarseClockCentreCalibration: CoarseClockCentreCalibration

        self.setattr_fragment("meas", NarrowDownAfterSliceFrag)
        self.meas: NarrowDownAfterSliceFrag
        # The optimizer re-measures many times inside one fix, so the measurement
        # owns its own lifecycle and channels (see the MOT calibrations).
        self.detach_fragment(self.meas)

        # The narrow up-slice gives the sharp centring peak; run the down_spec at
        # NORMAL power + duration so it fully de-shelves the shelved class. The
        # experiment's default is a deliberately weak, long (/100, 10x-pi) probe,
        # too under-powered to recover atoms - it tanks SNR (Charles, 2026-07-06).
        self.meas.override_param("p03_setpoint", _CLOCK_DELIVERY_INFO.setpoint)
        self.meas.override_param(
            "p04_pi_d_m1_down_spec_duration", constants.DOWN_CLOCK_BEAM_PI_TIME
        )

        coarse_seed = self.get_dataset(
            _COARSE_SEED_DATASET, default=_NOMINAL_DELIVERY_FREQUENCY, archive=False
        )
        self.setattr_param_optimizable(
            "delivery_frequency",
            "clock_delivery SUServo delivery AOM frequency",
            min=coarse_seed - _SEARCH_HALF_SPAN,
            max=coarse_seed + _SEARCH_HALF_SPAN,
            default=coarse_seed,
        )
        self.delivery_frequency: FloatParamHandle

        self.setattr_param(
            "min_ok_excitation",
            FloatParam,
            "excitation_fraction threshold for OK",
            default='dataset("calibrations.ClockDeliveryAOMCalibration.min_ok_excitation", default=1.0)',
        )
        self.min_ok_excitation: FloatParamHandle

        # Average a few shots to tighten the fitted carrier centre (the narrow
        # up-slice signal is real but shot-to-shot noisy).
        self.setattr_param(
            "num_averages",
            IntParam,
            "Shots averaged per delivery-frequency check",
            default=5,
        )
        self.num_averages: IntParamHandle

        # Clock delivery drifts ~1 kHz/day (<< the narrow-pulse linewidth per
        # hour), but a relock can jump it; re-check hourly.
        self.set_timeout(3600.0)
        self.set_optimization_type("max")
        self.set_optimizer(_delivery_fit_optimizer)

        self._excitation_sink = LastValueSink()
        self.meas.excitation_fraction.set_sink(self._excitation_sink)
        self._delivery_store = None
        self._armed = False

    @kernel
    def _measure(self):
        self.core.break_realtime()
        self.meas.device_setup()
        self.meas.run_once()
        self.meas.device_cleanup()

    def check_own_state(self):
        if self._delivery_store is None:
            _, self._delivery_store = self.meas.clock_default_setter.override_param(
                "frequency_clock_delivery", self.delivery_frequency.get()
            )
        self._delivery_store.set_value(self.delivery_frequency.get())

        # Arm the (detached) measurement lazily, ONCE per process (the imaging
        # wrapper does not survive a host_setup/host_cleanup/host_setup cycle;
        # see the MOT calibrations).
        if not self._armed:
            self.meas.host_setup()
            self._armed = True

        samples = []
        for _ in range(int(self.num_averages.get())):
            self._measure()
            value = self._excitation_sink.get_last()
            if value is not None:
                samples.append(value)
        if not samples:
            return CalibrationResult.INVALID_DATA, 0.0
        excitation = float(np.mean(samples))

        logger.info(
            "Clock delivery check: %.6f MHz -> excitation %.3f",
            1e-6 * self.delivery_frequency.get(),
            excitation,
        )
        if excitation >= self.min_ok_excitation.get():
            return CalibrationResult.OK, float(excitation)
        return CalibrationResult.BAD_DATA, float(excitation)


ClockDeliveryAOMCalibrationExp = make_fragment_scan_exp(ClockDeliveryAOMCalibration)
