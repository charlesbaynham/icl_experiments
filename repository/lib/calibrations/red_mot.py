import functools
import logging

from artiq.coredevice.core import Core
from artiq.experiment import kernel
from ndscan.experiment.entry_point import make_fragment_scan_exp
from ndscan.experiment.fragment import TransitoryError
from ndscan.experiment.parameters import FloatParam
from ndscan.experiment.parameters import FloatParamHandle
from ndscan.experiment.result_channels import LastValueSink

from qbutler.calibration import Calibration
from qbutler.calibration import CalibrationResult
from qbutler.optimizers import coordinate_descent_optimizer
from repository.lib import constants
from repository.lib.calibrations.blue_mot import BlueMOTCalibration
from repository.lib.experiment_templates.mixins.andor_imaging.bg_corrected_andor_image import (
    BGCorrectedAndorImageMixin,
)
from repository.red_mot.measure_red_mot import _MeasureNarrowbandMOTFrag

logger = logging.getLogger(__name__)

_AOM_DEFAULT = constants.URUKULED_BEAMS["red_doublepass_injection"].frequency


class _RedMOTAndorOnlyMeasFrag(BGCorrectedAndorImageMixin, _MeasureNarrowbandMOTFrag):
    """Narrowband red MOT + BG-corrected Andor imaging, WITHOUT the FLIR
    mixin: the FLIRs stay free for the blue calibration's measurement (one
    GigE control channel per camera, and the wrapper can't re-arm)."""


class RedMOTCalibration(Calibration):
    """The narrowband red MOT loads well; optimizes 689 AOM frequency and
    narrowband bias fields.

    Depends on :class:`BlueMOTCalibration` — a red MOT needs a healthy blue
    MOT to load from, and this calibration feeds the blue-optimized push
    setpoint into its own loading stage.

    Metric: background-corrected Andor fluorescence sum of the in-situ
    narrowband MOT (no dipole trap needed). Four optimizable parameters, so
    the optimizer is a coordinate descent (7 points/axis, 2 rounds = 56
    shots) rather than a grid.
    """

    def build_calibration(self):
        self.setattr_device("core")
        self.core: Core

        self.add_dependency(BlueMOTCalibration)
        self.BlueMOTCalibration: BlueMOTCalibration

        self.setattr_fragment("meas", _RedMOTAndorOnlyMeasFrag)
        self.meas: _RedMOTAndorOnlyMeasFrag
        self.detach_fragment(self.meas)

        self.setattr_param_optimizable(
            "aom_frequency",
            "689 injection AOM static frequency",
            min=_AOM_DEFAULT - 200e3,
            max=_AOM_DEFAULT + 200e3,
            default=_AOM_DEFAULT,
        )
        self.aom_frequency: FloatParamHandle

        self.setattr_param_optimizable(
            "bias_x",
            "Narrowband bias X",
            min=constants.RED_NARROWBAND_BIAS_FIELD_X - 0.15,
            max=constants.RED_NARROWBAND_BIAS_FIELD_X + 0.15,
            default=constants.RED_NARROWBAND_BIAS_FIELD_X,
        )
        self.bias_x: FloatParamHandle

        self.setattr_param_optimizable(
            "bias_y",
            "Narrowband bias Y",
            min=constants.RED_NARROWBAND_BIAS_FIELD_Y - 0.15,
            max=constants.RED_NARROWBAND_BIAS_FIELD_Y + 0.15,
            default=constants.RED_NARROWBAND_BIAS_FIELD_Y,
        )
        self.bias_y: FloatParamHandle

        self.setattr_param_optimizable(
            "bias_z",
            "Narrowband bias Z",
            min=constants.RED_NARROWBAND_BIAS_FIELD_Z - 0.3,
            max=constants.RED_NARROWBAND_BIAS_FIELD_Z + 0.3,
            default=constants.RED_NARROWBAND_BIAS_FIELD_Z,
        )
        self.bias_z: FloatParamHandle

        self.setattr_param(
            "min_ok_atom_sum",
            FloatParam,
            "andor_sum_bg_corrected threshold for OK",
            default=constants.RED_MOT_MIN_OK_ATOM_SUM,
        )
        self.min_ok_atom_sum: FloatParamHandle

        self.set_timeout(1800.0)
        self.set_optimization_type("max")
        self.set_optimizer(
            functools.partial(coordinate_descent_optimizer, num_points=7, n_rounds=2)
        )

        self._atom_sum_sink = LastValueSink()
        self.meas.andor_sum_bg_corrected.set_sink(self._atom_sum_sink)
        self._stores = None
        self._armed = False

    def _ensure_stores(self):
        if self._stores is None:
            self._stores = {}
            _, self._stores["aom_frequency"] = self.meas.override_param(
                "injection_aom_static_frequency", self.aom_frequency.get()
            )
            for axis in "xyz":
                _, self._stores[f"bias_{axis}"] = self.meas.red_mot.override_param(
                    f"narrowband_bias_{axis}", getattr(self, f"bias_{axis}").get()
                )
            # The blue-MOT stage of this sequence follows the blue calibration
            _, self._stores["push_setpoint"] = (
                self.meas.blue_3d_mot.all_beam_default_setter.override_param(
                    "setpoint_blue_push_beam",
                    self.BlueMOTCalibration.push_setpoint.get(),
                )
            )
            # NB the atom-number retry check (enable_check) defaults to False;
            # if enabled it would raise TransitoryError straight through our
            # manual kernel call - caught in check_own_state as BAD_DATA

    @kernel
    def _measure(self):
        self.core.break_realtime()
        self.meas.device_setup()
        self.meas.run_once()
        self.meas.device_cleanup()

    def check_own_state(self):
        self._ensure_stores()
        self._stores["aom_frequency"].set_value(self.aom_frequency.get())
        for axis in "xyz":
            self._stores[f"bias_{axis}"].set_value(getattr(self, f"bias_{axis}").get())
        self._stores["push_setpoint"].set_value(
            self.BlueMOTCalibration.push_setpoint.get()
        )

        # Arm the (detached) measurement lazily, once per process
        # (see BlueMOTCalibration.check_own_state)
        if not self._armed:
            self.meas.host_setup()
            self._armed = True
        try:
            self._measure()
        except TransitoryError:
            return CalibrationResult.BAD_DATA, 0.0

        atom_sum = self._atom_sum_sink.get_last()
        if atom_sum is None:
            return CalibrationResult.INVALID_DATA, 0.0

        logger.info(
            "Red MOT check: AOM %.6f MHz, bias (%.3f, %.3f, %.3f) A -> sum %.3g",
            1e-6 * self.aom_frequency.get(),
            self.bias_x.get(),
            self.bias_y.get(),
            self.bias_z.get(),
            atom_sum,
        )
        if atom_sum >= self.min_ok_atom_sum.get():
            return CalibrationResult.OK, float(atom_sum)
        return CalibrationResult.BAD_DATA, float(atom_sum)


RedMOTCalibrationExp = make_fragment_scan_exp(RedMOTCalibration)
