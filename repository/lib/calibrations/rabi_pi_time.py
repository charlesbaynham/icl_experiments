import logging

import numpy as np
from artiq.coredevice.core import Core
from artiq.experiment import kernel
from ndscan.experiment.entry_point import make_fragment_scan_exp
from ndscan.experiment.parameters import FloatParam
from ndscan.experiment.parameters import FloatParamHandle
from ndscan.experiment.result_channels import LastValueSink

from qbutler.calibration import Calibration
from qbutler.calibration import CalibrationResult
from repository.lib import constants
from repository.lib.calibrations._fit_helpers import fit_peak_x
from repository.lib.calibrations.clock_delivery import ClockDeliveryAOMCalibration
from repository.LMT.lmt_clock_ratio_calibration import DeclarativeClockRatioCalDownFrag
from repository.LMT.lmt_clock_ratio_calibration import DeclarativeClockRatioCalUpFrag

logger = logging.getLogger(__name__)

#: Points in one probe-duration sweep during a fix. 31 over [1 us, 2.5 x pi_nom]
#: resolves the flop (>1 full oscillation) with ~12 points up to the first max.
_SWEEP_POINTS = 31

#: Fractional band around the nominal (anchor) pi time within which a fitted pi
#: time is trusted; outside it, flag rather than silently persist.
_SANE_BAND = 0.4


def _make_rabi_flop_optimizer(nominal_pi_time):
    """Build a qbutler optimizer generator that sweeps the probe duration once,
    finds the first Rabi-flop maximum (= pi time) by a parabolic peak fit, and
    returns it -- unless it lands outside the sane band, in which case it returns
    None so the framework raises rather than persisting a bad value.
    """

    def _optimizer(param_specs):
        (spec,) = param_specs
        durations = np.linspace(spec.min, spec.max, _SWEEP_POINTS)

        excitations = []
        for t in durations:
            _, data = yield {spec.name: float(t)}
            excitations.append(data if isinstance(data, (int, float)) else np.nan)

        pi_time = fit_peak_x(durations, excitations)
        if pi_time is None:
            logger.warning("Rabi flop fit failed: no finite excitation data")
            return None

        lo, hi = (1 - _SANE_BAND) * nominal_pi_time, (1 + _SANE_BAND) * nominal_pi_time
        if not (lo <= pi_time <= hi):
            logger.warning(
                "Fitted pi time %.2f us outside sane band [%.2f, %.2f] us "
                "(nominal %.2f); not persisting",
                1e6 * pi_time,
                1e6 * lo,
                1e6 * hi,
                1e6 * nominal_pi_time,
            )
            return None

        logger.info("Rabi flop fit: pi time %.2f us", 1e6 * pi_time)
        return {spec.name: float(pi_time)}

    return _optimizer


class _RabiPiTimeCalibrationBase(Calibration):
    """Measure the Rabi pi time on one clock beam after a STATIC velocity slice.

    Only the probe-pulse duration is scanned; the slice pulse duration is left at
    its default, so the slice velocity class is invariant across the scan (a Rabi
    flop, not nonsense). Re-pumped imaging reads out the flop independently of any
    clock parameter. Depends on :class:`ClockDeliveryAOMCalibration` -- a pi time is
    only trustworthy once the delivery is centred.

    Subclasses set the measurement fragment, the probe-duration handle name, and
    the nominal pi time (anchor + fallback default).
    """

    _meas_frag_class = None
    _probe_duration_handle = None
    _nominal_pi_time = None

    def build_calibration(self):
        self.setattr_device("core")
        self.core: Core

        self.add_dependency(ClockDeliveryAOMCalibration)
        self.ClockDeliveryAOMCalibration: ClockDeliveryAOMCalibration

        self.setattr_fragment("meas", self._meas_frag_class)
        self.meas: self._meas_frag_class
        self.detach_fragment(self.meas)

        self.setattr_param_optimizable(
            "pi_time",
            "Clock Rabi pi time (probe pulse)",
            min=1e-6,
            max=2.5 * self._nominal_pi_time,
            default=self._nominal_pi_time,
        )
        self.pi_time: FloatParamHandle

        self.setattr_param(
            "min_ok_excitation",
            FloatParam,
            "excitation_fraction threshold for OK at the pi time",
            default=(
                'dataset("calibrations.'
                + self.__class__.__name__
                + '.min_ok_excitation", default=1.0)'
            ),
        )
        self.min_ok_excitation: FloatParamHandle

        self.set_timeout(3600.0)
        self.set_optimization_type("max")
        self.set_optimizer(_make_rabi_flop_optimizer(self._nominal_pi_time))

        self._excitation_sink = LastValueSink()
        self.meas.excitation_fraction.set_sink(self._excitation_sink)
        self._probe_store = None
        self._armed = False

    @kernel
    def _measure(self):
        self.core.break_realtime()
        self.meas.device_setup()
        self.meas.run_once()
        self.meas.device_cleanup()

    def check_own_state(self):
        if self._probe_store is None:
            _, self._probe_store = self.meas.override_param(
                self._probe_duration_handle, self.pi_time.get()
            )
        self._probe_store.set_value(self.pi_time.get())

        if not self._armed:
            self.meas.host_setup()
            self._armed = True
        self._measure()

        excitation = self._excitation_sink.get_last()
        if excitation is None:
            return CalibrationResult.INVALID_DATA, 0.0

        logger.info(
            "%s check: pi time %.2f us -> excitation %.3f",
            self.__class__.__name__,
            1e6 * self.pi_time.get(),
            excitation,
        )
        if excitation >= self.min_ok_excitation.get():
            return CalibrationResult.OK, float(excitation)
        return CalibrationResult.BAD_DATA, float(excitation)


class RabiUpPiTimeCalibration(_RabiPiTimeCalibrationBase):
    """Up-beam clock Rabi pi time (static slice, probe-duration scan)."""

    _meas_frag_class = DeclarativeClockRatioCalUpFrag
    _probe_duration_handle = "p04_pi_u_m1_probe_duration"
    _nominal_pi_time = constants.CLOCK_PI_TIME


class RabiDownPiTimeCalibration(_RabiPiTimeCalibrationBase):
    """Down-beam clock Rabi pi time (static slice, probe-duration scan)."""

    _meas_frag_class = DeclarativeClockRatioCalDownFrag
    _probe_duration_handle = "p04_pi_d_mn1_probe_duration"
    _nominal_pi_time = constants.DOWN_CLOCK_BEAM_PI_TIME


RabiUpPiTimeCalibrationExp = make_fragment_scan_exp(RabiUpPiTimeCalibration)
RabiDownPiTimeCalibrationExp = make_fragment_scan_exp(RabiDownPiTimeCalibration)
