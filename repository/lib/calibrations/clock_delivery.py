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
from repository.lib.calibrations._fit_helpers import fit_peak_x
from repository.lib import constants
from repository.LMT.lmt_tune_slice import NarrowDownAfterSliceFrag

logger = logging.getLogger(__name__)

_CLOCK_DELIVERY_INFO = constants.SUSERVOED_BEAMS["clock_delivery"]
_NOMINAL_DELIVERY_FREQUENCY = _CLOCK_DELIVERY_INFO.frequency

#: Half-width of the delivery-frequency search window. A post-relock drift can be
#: tens of kHz; the narrow down_spec pulse is Fourier-narrow, so the centre must
#: be found precisely within this window.
_SEARCH_HALF_SPAN = 100e3

#: Points in one delivery-frequency sweep during a fix (+/-100 kHz over 41 points
#: = 5 kHz grid, refined to sub-grid precision by the parabolic peak fit below).
_SWEEP_POINTS = 41


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
    offset), so its frequency is the common-mode centring knob. A velocity-
    selecting up-slice followed by a deliberately weak, long (Fourier-narrow) down
    pulse -- :class:`NarrowDownAfterSliceFrag` -- is hypersensitive to the delivery
    centring; re-pumped imaging reads out the survivors independently of any clock
    parameter, so the peak of the excitation fraction versus delivery frequency
    locates the centred frequency.

    Optimizable parameter: the ``frequency_clock_delivery`` SUServo delivery
    frequency (persisted to dataset
    ``calibrations.ClockDeliveryAOMCalibration.delivery_frequency``; ``constants.py``
    holds the fallback default). The narrow down pulse gives the sharp centring peak.
    """

    def build_calibration(self):
        self.setattr_device("core")
        self.core: Core

        self.setattr_fragment("meas", NarrowDownAfterSliceFrag)
        self.meas: NarrowDownAfterSliceFrag
        # The optimizer re-measures many times inside one fix, so the measurement
        # owns its own lifecycle and channels (see the MOT calibrations).
        self.detach_fragment(self.meas)

        self.setattr_param_optimizable(
            "delivery_frequency",
            "clock_delivery SUServo delivery AOM frequency",
            min=_NOMINAL_DELIVERY_FREQUENCY - _SEARCH_HALF_SPAN,
            max=_NOMINAL_DELIVERY_FREQUENCY + _SEARCH_HALF_SPAN,
            default=_NOMINAL_DELIVERY_FREQUENCY,
        )
        self.delivery_frequency: FloatParamHandle

        self.setattr_param(
            "min_ok_excitation",
            FloatParam,
            "excitation_fraction threshold for OK",
            default='dataset("calibrations.ClockDeliveryAOMCalibration.min_ok_excitation", default=1.0)',
        )
        self.min_ok_excitation: FloatParamHandle

        # Clock delivery drifts ~1 kHz/day (<< the narrow-pulse linewidth per
        # hour), but a relock can jump it; re-check hourly.
        self.set_timeout(3600.0)
        self.set_optimization_type("max")
        self.set_optimizer(_delivery_fit_optimizer)

        self._excitation_sink = LastValueSink()
        self.meas.excitation_fraction.set_sink(self._excitation_sink)
        self._delivery_store = None
        self._armed = False
        self._measure_precompiled = None

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
        if self._measure_precompiled is None:
            self._measure_precompiled = self.core.precompile(self._measure)
        self._measure_precompiled()

        excitation = self._excitation_sink.get_last()
        if excitation is None:
            return CalibrationResult.INVALID_DATA, 0.0

        logger.info(
            "Clock delivery check: %.6f MHz -> excitation %.3f",
            1e-6 * self.delivery_frequency.get(),
            excitation,
        )
        if excitation >= self.min_ok_excitation.get():
            return CalibrationResult.OK, float(excitation)
        return CalibrationResult.BAD_DATA, float(excitation)


ClockDeliveryAOMCalibrationExp = make_fragment_scan_exp(ClockDeliveryAOMCalibration)
