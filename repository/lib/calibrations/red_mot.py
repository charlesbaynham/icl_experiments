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
from repository.lib.calibrations.blue_mot import PUSH_SETPOINT_DEFAULT
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
    """The narrowband red MOT loads well; optimizes the 689 injection AOM
    frequency.

    Depends on :class:`BlueMOTCalibration` -- a red MOT needs a healthy blue
    MOT to load from, and this calibration feeds the blue-optimized push
    setpoint into its own loading stage.

    Metric: background-corrected Andor fluorescence sum of the in-situ
    narrowband MOT (no dipole trap needed).

    ``check_own_state`` is a kernel, and the default (grid-search) optimizer is
    batchable, so a fix sweep runs in a single kernel call -- one compile, one
    upload -- instead of recompiling per point.
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

        self.setattr_param(
            "min_ok_atom_sum",
            FloatParam,
            "andor_sum_bg_corrected threshold for OK",
            default='dataset("calibrations.RedMOTCalibration.min_ok_atom_sum", default=1.0e12)',
        )
        self.min_ok_atom_sum: FloatParamHandle

        self.set_timeout(1800.0)
        self.set_optimization_type("max")

        self._atom_sum_sink = LastValueSink()
        self.meas.andor_sum_bg_corrected.set_sink(self._atom_sum_sink)

        # Bind the swept AOM frequency and the (blue-optimized) push setpoint to
        # stores now, at build time, so the kernel can set them on-core. The
        # initial values are placeholders that check_own_state overwrites on-core
        # (params aren't readable via .get() until init_params(), after build).
        _, self._aom_store = self.meas.override_param(
            "injection_aom_static_frequency", _AOM_DEFAULT
        )
        _, self._push_store = (
            self.meas.blue_3d_mot.all_beam_default_setter.override_param(
                "setpoint_blue_push_beam", PUSH_SETPOINT_DEFAULT
            )
        )
        self._armed = False

    def host_setup(self):
        super().host_setup()
        # Arm the whole calibration chain (this node + its blue-MOT dependency)
        # here, on the host: the measurements are detached, and their kernels
        # read attributes set in host_setup, which must exist before
        # check_own_state compiles (see BlueMOTCalibration).
        for cal in dag.get_dependencies(self):
            cal._ensure_armed()

    def _ensure_armed(self):
        # Arm the (detached) measurement once per process (see BlueMOTCalibration).
        if not self._armed:
            self.meas.host_setup()
            self._armed = True

    @rpc
    def _read_atom_sum(self, aom_frequency: TFloat) -> TFloat:
        s = self._atom_sum_sink.get_last()
        if s is None:
            return float("nan")
        logger.info("Red MOT check: AOM %.6f MHz -> sum %.3g", 1e-6 * aom_frequency, s)
        return float(s)

    @kernel
    def check_own_state(self):
        aom_frequency = self.aom_frequency.get()
        self._aom_store.set_value(aom_frequency)
        # Blue's committed push setpoint is fixed during our sweep; feed it in.
        self._push_store.set_value(self.BlueMOTCalibration.push_setpoint.get())

        self.core.break_realtime()
        self.meas.device_setup()
        self.meas.run_once()
        self.meas.device_cleanup()

        atom_sum = self._read_atom_sum(aom_frequency)
        if atom_sum != atom_sum:  # NaN: the measurement produced no data
            return CalibrationResult.INVALID_DATA, 0.0
        if atom_sum >= self.min_ok_atom_sum.get():
            return CalibrationResult.OK, atom_sum
        return CalibrationResult.BAD_DATA, atom_sum


RedMOTCalibrationExp = make_fragment_scan_exp(RedMOTCalibration)
