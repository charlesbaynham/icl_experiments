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
from repository.lib.experiment_templates.mixins.andor_imaging.bg_corrected_andor_image import (
    BGCorrectedAndorImageSingleXODTMixin,
)
from repository.lib.experiment_templates.mixins.XODT_loading import LoadSingleXODTMixin

logger = logging.getLogger(__name__)

_Z_FIELD_DEFAULT = constants.RED_NARROWBAND_BIAS_FIELD_Z


class _SimpleSingleXODTBGCorrectedFrag(
    BGCorrectedAndorImageSingleXODTMixin,
    LoadSingleXODTMixin,
):

    @kernel
    def DMA_initialization_hook(self):
        self.DMA_initialization_hook_redmot_default()
        self.DMA_initialization_hook_loading_xodt_mot()
        self.DMA_initialization_hook_dipole_trap_default()

    @kernel
    def do_experiment_after_dipole_trap_hook(self):
        pass


class SingleXODTCalibration(InfluxRecalibrationLogMixin, Calibration):
    """Check that the XODT is working; optimizes the Z bias field current
    used during the final (narrowband) stage of the red MOT that loads the
    XODT.
    """

    def build_calibration(self):
        self.setattr_device("core")
        self.core: Core

        self.add_dependency(RedMOTCalibration)
        self.RedMOTCalibration: RedMOTCalibration

        self.set_timeout(3600.0)
        self.set_optimization_type("max")

        self.setattr_param(
            "min_ok_fluorescence",
            FloatParam,
            "fluorescence threshold for OK",
            default=1e6,  # FIXME to constants
        )
        self.min_ok_fluorescence: FloatParamHandle

        self.setattr_fragment("meas", _SimpleSingleXODTBGCorrectedFrag)
        self.meas: _SimpleSingleXODTBGCorrectedFrag
        # The optimizer re-measures many times inside one fix, so the measurement
        # owns its own lifecycle and channels (see the MOT calibrations).
        self.detach_fragment(self.meas)

        self.setattr_param_optimizable(
            "xodt_z_field",
            "Z bias field current during the final narrowband red MOT stage",
            min=_Z_FIELD_DEFAULT - 0.2,
            max=_Z_FIELD_DEFAULT + 0.2,
            default=_Z_FIELD_DEFAULT,
            unit="A",
        )
        self.xodt_z_field: FloatParamHandle

        # Bind the swept Z field to a store now, at build time, so the kernel
        # can set it on-core (params aren't readable via .get() until
        # init_params(), after build; see RedMOTCalibration).
        _, self._z_field_store = self.meas.red_mot.override_param(
            "narrowband_bias_z", _Z_FIELD_DEFAULT
        )

        self._measurement_sink = LastValueSink()
        self.meas.andor_sum_bg_corrected.set_sink(self._measurement_sink)

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
    def _read_fluorescence(self) -> TFloat:  # type: ignore
        e = self._measurement_sink.get_last()
        if e is None:
            return float("nan")
        logger.info(
            "XODT check: fluorescence %.3f",
            e,
        )
        return float(e)

    @kernel
    def check_own_state(self):
        self._z_field_store.set_value(self.xodt_z_field.get())

        self.core.break_realtime()
        self.meas.device_setup()
        self.meas.run_once()
        self.meas.device_cleanup()

        fluorescence = self._read_fluorescence()
        if fluorescence != fluorescence:  # NaN: the measurement produced no data
            return CalibrationResult.INVALID_DATA, 0.0
        if fluorescence >= self.min_ok_fluorescence.get():
            return CalibrationResult.OK, fluorescence
        return CalibrationResult.BAD_DATA, fluorescence


SingleXODTCalibrationExp = make_fragment_scan_exp(SingleXODTCalibration)
