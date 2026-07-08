import logging

from artiq.coredevice.core import Core
from artiq.experiment import TFloat
from artiq.experiment import kernel
from artiq.experiment import rpc
from ndscan.experiment.entry_point import make_fragment_scan_exp
from ndscan.experiment.parameters import FloatParam
from ndscan.experiment.parameters import FloatParamHandle
from ndscan.experiment.result_channels import LastValueSink

from qbutler import dag
from qbutler.calibration import Calibration
from qbutler.calibration import CalibrationResult
from repository.lib import constants
from repository.lib.calibrations.influx_logging import InfluxRecalibrationLogMixin
from repository.lib.calibrations.clock_delivery import ClockDeliveryAOMCalibration
from repository.LMT.lmt_clock_ratio_calibration import DeclarativeClockRatioCalDownFrag
from repository.LMT.lmt_clock_ratio_calibration import DeclarativeClockRatioCalUpFrag

logger = logging.getLogger(__name__)


class _RabiPiTimeCalibrationBase(InfluxRecalibrationLogMixin, Calibration):
    """Measure the Rabi pi time on one clock beam after a STATIC velocity slice.

    Only the probe-pulse duration is scanned; the slice pulse duration is left at
    its default, so the slice velocity class is invariant across the scan (a Rabi
    flop, not nonsense). Re-pumped imaging reads out the flop independently of any
    clock parameter. Depends on :class:`ClockDeliveryAOMCalibration` -- a pi time is
    only trustworthy once the delivery is centred.

    The optimizer sweeps the probe duration and keeps the grid point of maximum
    excitation (the first Rabi-flop peak = pi time). ``check_own_state`` is a
    kernel and the default (grid-search) optimizer is batchable, so a fix sweep
    runs in a single kernel call.

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
            default=constants.CLOCK_RABI_MIN_OK_EXCITATION,
        )
        self.min_ok_excitation: FloatParamHandle

        self.set_timeout(3600.0)
        self.set_optimization_type("max")

        self._excitation_sink = LastValueSink()
        self.meas.excitation_fraction.set_sink(self._excitation_sink)

        # Bind the swept probe duration to a store now, at build time, so the
        # kernel can set it on-core. The initial value is a placeholder that
        # check_own_state overwrites on-core (params aren't readable via .get()
        # until init_params(), after build).
        _, self._probe_store = self.meas.override_param(
            self._probe_duration_handle, self._nominal_pi_time
        )
        self._armed = False

    def host_setup(self):
        super().host_setup()
        # Arm the whole calibration chain (this node + its clock-delivery
        # dependency) here, on the host: the measurements are detached, and their
        # kernels read attributes set in host_setup, which must exist before
        # check_own_state compiles (see the MOT calibrations).
        for cal in dag.get_dependencies(self):
            cal._ensure_armed()

    def _ensure_armed(self):
        # Arm the (detached) measurement once per process (see the MOT calibrations).
        if not self._armed:
            self.meas.host_setup()
            self._armed = True

    @rpc
    def _read_excitation(self, pi_time: TFloat) -> TFloat:
        e = self._excitation_sink.get_last()
        if e is None:
            return float("nan")
        logger.info(
            "%s check: pi time %.2f us -> excitation %.3f",
            self.__class__.__name__,
            1e6 * pi_time,
            e,
        )
        return float(e)

    @kernel
    def check_own_state(self):
        pi_time = self.pi_time.get()
        self._probe_store.set_value(pi_time)

        self.core.break_realtime()
        self.meas.device_setup()
        self.meas.run_once()
        self.meas.device_cleanup()

        excitation = self._read_excitation(pi_time)
        if excitation != excitation:  # NaN: the measurement produced no data
            return CalibrationResult.INVALID_DATA, 0.0
        if excitation >= self.min_ok_excitation.get():
            return CalibrationResult.OK, excitation
        return CalibrationResult.BAD_DATA, excitation


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
