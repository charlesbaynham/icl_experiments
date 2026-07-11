import logging

import numpy as np
from artiq.coredevice.core import Core
from artiq.experiment import TFloat
from artiq.experiment import kernel
from artiq.experiment import rpc
from ndscan.experiment.entry_point import make_fragment_scan_exp
from ndscan.experiment.parameters import FloatParam
from ndscan.experiment.parameters import FloatParamHandle
from ndscan.experiment.parameters import IntParam
from ndscan.experiment.parameters import IntParamHandle
from ndscan.experiment.result_channels import LastValueSink

from qbutler import dag
from qbutler.calibration import Calibration
from qbutler.calibration import CalibrationResult
from repository.lib import constants
from repository.lib.calibrations._fit_helpers import fit_peak_x
from repository.lib.calibrations.red_mot import RedMOTCalibration
from repository.lib.lmt_sequence import Beam
from repository.lib.lmt_sequence import SetPoint
from repository.lib.lmt_sequence import pi
from repository.lib.physics.lmt_resonance import GROUND
from repository.LMT_declarative.lmt_tune_slice import NarrowDownAfterSliceFrag

logger = logging.getLogger(__name__)

_CLOCK_DELIVERY_INFO = constants.SUSERVOED_BEAMS["clock_delivery"]
_NOMINAL_DELIVERY_FREQUENCY = _CLOCK_DELIVERY_INFO.frequency

#: Half-width of the coarse acquisition window. Deliberately wide: this node is
#: the line *finder* that seeds the narrow refined step, and the true carrier
#: wanders far from the SUServo nominal (historically ~99.44-99.49 MHz) as the
#: clock re-bakes. Compare the refined node's precision +/-30 kHz.
_SEARCH_HALF_SPAN = 125e3

#: Points in one coarse delivery-frequency sweep (~8 kHz grid). The feature is a
#: broad, power-broadened bump, so a coarse grid resolves it; the parabolic fit
#: refines the middle to sub-grid.
_SWEEP_POINTS = 31


class _CoarseClockLineFrag(NarrowDownAfterSliceFrag):
    """A single full-power clock pi on the whole XODT ground cloud.

    Reuses the declarative-LMT + repumped-readout machinery of
    :class:`NarrowDownAfterSliceFrag`, but replaces its velocity-slice +
    weak down_spec sequence with one NORMAL-power up-beam pi driven straight
    off the delivery setpoint. On the unsliced cloud this is Doppler- and
    power-broadened into a wide excitation bump versus delivery frequency -
    exactly the coarse line-finder this node needs, in contrast to the
    Fourier-narrow refined pulse.
    """

    lmt_initial_population = {(GROUND, 0)}

    lmt_sequence = [
        SetPoint(
            setpoint=_CLOCK_DELIVERY_INFO.setpoint,
            rabi_up=1 / (2 * constants.CLOCK_PI_TIME),
        ),
        pi(Beam.UP, m=0, label="coarse_spec"),
    ]


def _coarse_fit_optimizer(param_specs):
    """qbutler optimizer generator: sweep the delivery frequency once across the
    wide coarse window, then return the parabolic-fitted centre of the broad
    excitation bump as the best param (the seed for the refined node).
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


class CoarseClockCentreCalibration(Calibration):
    """Coarsely centre the shared clock ``clock_delivery`` SUServo delivery AOM.

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

    def build_calibration(self):
        self.setattr_device("core")
        self.core: Core

        self.add_dependency(RedMOTCalibration)
        self.RedMOTCalibration: RedMOTCalibration

        self.setattr_fragment("meas", _CoarseClockLineFrag)
        self.meas: _CoarseClockLineFrag
        # The optimizer re-measures many times inside one fix, so the
        # measurement owns its own lifecycle and channels (see the MOT/clock
        # calibrations).
        self.detach_fragment(self.meas)

        self.setattr_param_optimizable(
            "delivery_frequency",
            "clock_delivery SUServo delivery AOM frequency (coarse)",
            min=_NOMINAL_DELIVERY_FREQUENCY - _SEARCH_HALF_SPAN,
            max=_NOMINAL_DELIVERY_FREQUENCY + _SEARCH_HALF_SPAN,
            default=_NOMINAL_DELIVERY_FREQUENCY,
        )
        self.delivery_frequency: FloatParamHandle

        self.setattr_param(
            "min_ok_excitation",
            FloatParam,
            "excitation_fraction threshold for OK",
            default=constants.CLOCK_COARSE_MIN_OK_EXCITATION,
        )
        self.min_ok_excitation: FloatParamHandle

        self.setattr_param(
            "num_averages",
            IntParam,
            "Shots averaged per delivery-frequency check",
            default=1,
        )
        self.num_averages: IntParamHandle

        # A relock can jump the carrier; the broad feature drifts slowly. Re-find
        # hourly, matching the refined node's cadence.
        self.set_timeout(3600.0)
        self.set_optimization_type("max")
        self.set_optimizer(_coarse_fit_optimizer)

        self._excitation_sink = LastValueSink()
        self.meas.excitation_fraction.set_sink(self._excitation_sink)

        # Bind the swept delivery frequency to a store at build time so the
        # kernel can set it on-core (params aren't readable via .get() until
        # after build); check_own_state overwrites the value on-core.
        _, self._delivery_store = self.meas.clock_default_setter.override_param(
            "frequency_clock_delivery", _NOMINAL_DELIVERY_FREQUENCY
        )
        self._armed = False

    def host_setup(self):
        super().host_setup()
        # Arm the detached measurements on the host: their kernels read
        # attributes set in host_setup, which must exist before check_own_state
        # compiles (see the MOT / refined-clock calibrations).
        for cal in dag.get_dependencies(self):
            cal._ensure_armed()

    def _ensure_armed(self):
        # Arm the (detached) measurement once per process (the imaging wrapper
        # does not survive a host_setup/host_cleanup/host_setup cycle).
        if not self._armed:
            self.meas.host_setup()
            self._armed = True

    @rpc
    def _read_excitation(self, delivery_frequency: TFloat) -> TFloat:
        e = self._excitation_sink.get_last()
        if e is None:
            return float("nan")
        logger.info(
            "Coarse clock centre check: %.6f MHz -> excitation %.3f",
            1e-6 * delivery_frequency,
            e,
        )
        return float(e)

    @kernel
    def check_own_state(self):
        delivery_frequency = self.delivery_frequency.get()
        self._delivery_store.set_value(delivery_frequency)

        total = 0.0
        count = 0
        for _ in range(self.num_averages.get()):
            self.core.break_realtime()
            self.meas.device_setup()
            self.meas.run_once()
            self.meas.device_cleanup()
            excitation = self._read_excitation(delivery_frequency)
            if excitation == excitation:  # not NaN
                total += excitation
                count += 1

        if count == 0:
            return CalibrationResult.INVALID_DATA, 0.0
        mean_excitation = total / float(count)
        if mean_excitation >= self.min_ok_excitation.get():
            return CalibrationResult.OK, mean_excitation
        return CalibrationResult.BAD_DATA, mean_excitation


CoarseClockCentreCalibrationExp = make_fragment_scan_exp(CoarseClockCentreCalibration)
