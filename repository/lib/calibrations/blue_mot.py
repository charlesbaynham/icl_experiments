import logging

from artiq.coredevice.core import Core
from artiq.experiment import TFloat
from artiq.experiment import kernel
from artiq.experiment import rpc
from ndscan.experiment.parameters import FloatParam
from ndscan.experiment.parameters import FloatParamHandle
from ndscan.experiment.result_channels import LastValueSink

from qbutler import dag
from qbutler.calibration import Calibration
from qbutler.calibration import CalibrationResult
from repository.blue_mot.measure_blue_mot import MeasureBlueMOTBGCorrectedFrag
from repository.lib import constants
from repository.lib.calibrations.influx_logging import InfluxRecalibrationLogMixin

logger = logging.getLogger(__name__)

#: Nominal push-beam setpoint; the optimizer default and the initial value of the
#: hardware store (which check_own_state overwrites on-core every shot).
PUSH_SETPOINT_DEFAULT = 0.8


class BlueMOTCalibration(InfluxRecalibrationLogMixin, Calibration):
    """BlueMOTCalibration

    Metric: background-corrected vertical FLIR fluorescence after a normal
    MOT load. The acceptance threshold is
    ``constants.BLUE_MOT_MIN_OK_FLUORESCENCE``, so the node drives to green
    from constants alone.

    ``check_own_state`` is a kernel. The default (grid-search) optimizer is
    batchable, so a whole fix sweep runs in a single kernel call -- one compile
    and one upload -- instead of recompiling a measurement kernel per point.
    """

    def build_calibration(self):
        self.setattr_device("core")
        self.core: Core

        self.setattr_fragment("meas", MeasureBlueMOTBGCorrectedFrag)
        self.meas: MeasureBlueMOTBGCorrectedFrag
        # The optimizer re-measures many times inside one fix, so the
        # measurement owns its own lifecycle and channels, like a subscan.
        self.detach_fragment(self.meas)

        self.setattr_param_optimizable(
            "push_setpoint",
            "Push beam SUServo setpoint",
            min=0.0,
            max=2.0,
            default=PUSH_SETPOINT_DEFAULT,
        )
        self.push_setpoint: FloatParamHandle

        self.setattr_param(
            "min_ok_fluorescence",
            FloatParam,
            "bg-corrected image_vertical_mean threshold for OK",
            default=constants.BLUE_MOT_MIN_OK_FLUORESCENCE,
        )
        self.min_ok_fluorescence: FloatParamHandle

        self.set_timeout(300.0)  # 300s for testing only
        self.set_optimization_type("max")

        self._fluorescence_sink = LastValueSink()
        self.meas.bg_corrected_measurement.image_vertical_mean.set_sink(
            self._fluorescence_sink
        )

        # The push setpoint lives deep in the MOT controller. Bind it to a
        # store now, at build time, so the kernel can set it on-core: the
        # kernel embeds a reference to this store when it compiles. The initial
        # value is a placeholder -- check_own_state sets it on-core each shot --
        # and params aren't readable (.get()) until init_params(), after build.
        _, self._push_store = (
            self.meas.mot_controller.all_beam_default_setter.override_param(
                "setpoint_blue_push_beam", PUSH_SETPOINT_DEFAULT
            )
        )
        self._armed = False

    def host_setup(self):
        super().host_setup()
        # Arm the whole calibration chain here, on the host. The measurement is
        # detached, so ndscan won't arm it; and its kernels read attributes set
        # in host_setup (e.g. mirny_channels), which must exist before
        # check_own_state compiles. host_setup runs immediately before the
        # kernel, so this is the right hook.
        for cal in dag.get_dependencies(self):
            cal._ensure_armed()

    def _ensure_armed(self):
        # Arm the (detached) measurement once per process: the FLIR wrapper
        # does not survive a host_setup/host_cleanup/host_setup cycle (aravis
        # __getattr__ RecursionError), so never disarm.
        if not self._armed:
            self.meas.host_setup()
            self._armed = True

    @rpc
    def _read_fluorescence(self, setpoint: TFloat) -> TFloat:
        f = self._fluorescence_sink.get_last()
        if f is None:
            return float("nan")
        logger.info(
            "Blue MOT check: push setpoint %.3f V -> fluorescence %.3f", setpoint, f
        )
        return float(f)

    @kernel
    def check_own_state(self):
        setpoint = self.push_setpoint.get()
        self._push_store.set_value(setpoint)

        self.core.break_realtime()
        self.meas.device_setup()
        self.meas.run_once()
        self.meas.device_cleanup()

        fluorescence = self._read_fluorescence(setpoint)
        if fluorescence != fluorescence:  # NaN: the measurement produced no data
            return CalibrationResult.INVALID_DATA, 0.0
        if fluorescence >= self.min_ok_fluorescence.get():
            return CalibrationResult.OK, fluorescence
        return CalibrationResult.BAD_DATA, fluorescence
