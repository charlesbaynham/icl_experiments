"""Mixin that opens the calibration DAG applet for Ensure calibration clients."""

from artiq.master.worker_impl import CCB
from ndscan.experiment import ExpFragment

CALIBRATION_DAG_APPLET_CMD = (
    "${python} -m repository.lib.applets.qbutler_dag_applet "
    "calibrations.dag calibrations.status"
)


class CalibrationDAGAppletMixin(ExpFragment):
    """Open the calibration DAG applet in dashboard host setup."""

    def build_fragment(self):
        super().build_fragment()
        self.setattr_device("ccb")
        self.ccb: CCB

    def host_setup(self):
        super().host_setup()
        self.ccb.issue("create_applet", "Calibration DAG", CALIBRATION_DAG_APPLET_CMD)
