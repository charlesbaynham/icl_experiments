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
from repository.lib.calibrations.red_mot import RedMOTCalibration
from repository.LMT_declarative.lmt_tune_slice import NarrowDownAfterSliceFrag

logger = logging.getLogger(__name__)


class SingleXODTCalibration(InfluxRecalibrationLogMixin, Calibration):
    """Check that the XODT is working

    No optimisation here, just a check

    TODO: Add optimization
    """

    # FIXME WIP

    def build_calibration(self):
        self.setattr_device("core")
        self.core: Core

        self.add_dependency(RedMOTCalibration)
        self.RedMOTCalibration: RedMOTCalibration

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
            default=constants.CLOCK_REFINED_MIN_OK_EXCITATION,
        )
        self.min_ok_excitation: FloatParamHandle

        # Clock delivery drifts ~1 kHz/day (<< the narrow-pulse linewidth per
        # hour), but a relock can jump it; re-check hourly.
        self.set_timeout(3600.0)
        self.set_optimization_type("max")

        self._excitation_sink = LastValueSink()
        self.meas.excitation_fraction.set_sink(self._excitation_sink)

        # Bind the swept delivery frequency to a store now, at build time, so the
        # kernel can set it on-core. The initial value is a placeholder that
        # check_own_state overwrites on-core (params aren't readable via .get()
        # until init_params(), after build).
        _, self._delivery_store = self.meas.clock_default_setter.override_param(
            "frequency_clock_delivery", _NOMINAL_DELIVERY_FREQUENCY
        )
        self._armed = False

    def host_setup(self):
        super().host_setup()
        # Arm the detached measurement here, on the host: its kernels read
        # attributes set in host_setup, which must exist before check_own_state
        # compiles (see the MOT calibrations).
        for cal in dag.get_dependencies(self):
            cal._ensure_armed()

    def _ensure_armed(self):
        # Arm the (detached) measurement once per process (the imaging wrapper
        # does not survive a host_setup/host_cleanup/host_setup cycle; see the
        # MOT calibrations).
        if not self._armed:
            self.meas.host_setup()
            self._armed = True

    @rpc
    def _read_excitation(self, delivery_frequency: TFloat) -> TFloat:
        e = self._excitation_sink.get_last()
        if e is None:
            return float("nan")
        logger.info(
            "Clock delivery check: %.6f MHz -> excitation %.3f",
            1e-6 * delivery_frequency,
            e,
        )
        return float(e)

    @kernel
    def check_own_state(self):
        delivery_frequency = self.delivery_frequency.get()
        self._delivery_store.set_value(delivery_frequency)

        self.core.break_realtime()
        self.meas.device_setup()
        self.meas.run_once()
        self.meas.device_cleanup()

        excitation = self._read_excitation(delivery_frequency)
        if excitation != excitation:  # NaN: the measurement produced no data
            return CalibrationResult.INVALID_DATA, 0.0
        if excitation >= self.min_ok_excitation.get():
            return CalibrationResult.OK, excitation
        return CalibrationResult.BAD_DATA, excitation


ClockDeliveryAOMCalibrationExp = make_fragment_scan_exp(ClockDeliveryAOMCalibration)
