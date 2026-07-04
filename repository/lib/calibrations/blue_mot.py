import logging

from artiq.coredevice.core import Core
from artiq.experiment import kernel
from ndscan.experiment.entry_point import make_fragment_scan_exp
from ndscan.experiment.parameters import FloatParam
from ndscan.experiment.parameters import FloatParamHandle
from ndscan.experiment.result_channels import LastValueSink

from qbutler.calibration import Calibration
from qbutler.calibration import CalibrationResult
from repository.blue_mot.measure_blue_mot import MeasureBlueMOTBGCorrectedFrag

logger = logging.getLogger(__name__)


class BlueMOTCalibration(Calibration):
    """The blue MOT loads well; optimizes the push-beam SUServo setpoint.

    Metric: background-corrected vertical FLIR fluorescence after a normal
    MOT load. The threshold parameter defaults (via dataset) to an impossibly
    high value so the calibration fails closed until it has been set from
    live data.
    """

    def build_calibration(self):
        self.setattr_device("core")
        self.core: Core

        self.setattr_fragment("meas", MeasureBlueMOTBGCorrectedFrag)
        self.meas: MeasureBlueMOTBGCorrectedFrag
        # The optimizer re-measures many times inside one scan point, so the
        # measurement must own its lifecycle and channels, like a subscan
        self.detach_fragment(self.meas)

        self.setattr_param_optimizable(
            "push_setpoint",
            "Push beam SUServo setpoint",
            min=0.0,
            max=2.0,
            default=0.8,
        )
        self.push_setpoint: FloatParamHandle

        self.setattr_param(
            "min_ok_fluorescence",
            FloatParam,
            "bg-corrected image_vertical_mean threshold for OK",
            default='dataset("calibrations.BlueMOTCalibration.min_ok_fluorescence", default=1.0e9)',
        )
        self.min_ok_fluorescence: FloatParamHandle

        self.set_timeout(1800.0)
        self.set_optimization_type("max")

        self._fluorescence_sink = LastValueSink()
        self._push_store = None

    def host_setup(self):
        super().host_setup()
        self.meas.host_setup()

        self.meas.bg_corrected_measurement.image_vertical_mean.set_sink(
            self._fluorescence_sink
        )
        if self._push_store is None:
            _, self._push_store = (
                self.meas.mot_controller.all_beam_default_setter.override_param(
                    "setpoint_blue_push_beam", self.push_setpoint.get()
                )
            )

    def host_cleanup(self):
        self.meas.host_cleanup()
        super().host_cleanup()

    @kernel
    def _measure(self):
        self.core.break_realtime()
        self.meas.device_setup()
        self.meas.run_once()
        self.meas.device_cleanup()

    def check_own_state(self):
        self._push_store.set_value(self.push_setpoint.get())
        self._measure()

        fluorescence = self._fluorescence_sink.get_last()
        if fluorescence is None:
            return CalibrationResult.INVALID_DATA, 0.0

        logger.info(
            "Blue MOT check: push setpoint %.3f V -> fluorescence %.3f",
            self.push_setpoint.get(),
            fluorescence,
        )
        if fluorescence >= self.min_ok_fluorescence.get():
            return CalibrationResult.OK, float(fluorescence)
        return CalibrationResult.BAD_DATA, float(fluorescence)


BlueMOTCalibrationExp = make_fragment_scan_exp(BlueMOTCalibration)
