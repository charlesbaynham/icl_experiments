"""Sample unit tests"""
import importlib
import pkgutil
from pathlib import Path

import pytest

path_to_repo = Path(__file__, "../../repository").resolve()


@pytest.mark.parametrize(
    "module_name",
    [
        name
        for _, name, _ in pkgutil.walk_packages([str(path_to_repo)], "repository" + ".")
    ],
)
def test_import_all_modules(module_name):
    importlib.import_module(module_name)


def test_device_db():
    from device_db import device_db

    print(device_db)

    assert "core" in device_db
    assert "core_log" in device_db
    assert "influx_logger" in device_db


@pytest.mark.slow
def test_slow():
    print("This is a very slow test which will sometimes be skipped (see the readme)")
    assert True
