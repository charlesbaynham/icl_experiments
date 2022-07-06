"""Sample unit tests"""
import importlib
import pkgutil

import icl_aion
import pytest


def test_pass():
    from icl_aion.hello import hello

    hello()


@pytest.mark.parametrize(
    "module_name",
    [
        name
        for _, name, _ in pkgutil.walk_packages(
            icl_aion.__path__, icl_aion.__name__ + "."
        )
    ],
)
def test_import_all_modules(module_name):
    importlib.import_module(module_name)


@pytest.mark.slow
def test_slow():
    print("This is a very slow test which will sometimes be skipped (see the readme)")
    assert True
