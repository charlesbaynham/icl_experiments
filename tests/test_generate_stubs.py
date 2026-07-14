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
