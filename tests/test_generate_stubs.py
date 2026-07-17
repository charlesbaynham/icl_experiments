import importlib.util
import pathlib

MODULE_PATH = (
    pathlib.Path(__file__).resolve().parents[1] / "scripts" / "generate_stubs.py"
)
SPEC = importlib.util.spec_from_file_location("generate_stubs", MODULE_PATH)
assert SPEC is not None and SPEC.loader is not None

generate_stubs = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(generate_stubs)


def test_monitor_controller_assignments_are_discovered():
    sources = {
        "repository/monitors/monitor_master.py": """
from qbutler.monitoring import make_monitor_controller

MonitorMaster = make_monitor_controller(
    "MonitorMaster",
    monitors={},
    devices=["influx_logger"],
    data_logger=None,
)
"""
    }

    experiments = generate_stubs.enumerate_experiments("master", sources)

    assert any(exp.name == "MonitorMaster" for exp in experiments)


def test_calibrated_experiments_are_discovered():
    sources = {
        "repository/calibrations/ensure_blue_mot.py": '''
from qbutler import CalibratedExpFragment
from qbutler import make_calibrated_experiment


class EnsureBlueMOTFrag(CalibratedExpFragment):
    """Check the blue-MOT calibration and fix it if required."""

    def build_fragment(self):
        pass


EnsureBlueMOT = make_calibrated_experiment(EnsureBlueMOTFrag)
'''
    }

    experiments = generate_stubs.enumerate_experiments("master", sources)

    assert any(
        exp.name == "EnsureBlueMOT"
        and exp.docstring == "Check the blue-MOT calibration and fix it if required."
        for exp in experiments
    )
