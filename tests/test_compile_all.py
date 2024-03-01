"""
Get all Fragments from the repository and attempt to compile them with their
default settings
"""

import importlib
import inspect
import pkgutil
from pathlib import Path

import pytest
from ndscan.experiment import ExpFragment
from qbutler.calibration import Calibration

path_to_repo = Path(__file__, "../../repository").resolve()


def get_all_repo_modules():
    out = []

    for _, name, _ in pkgutil.walk_packages([str(path_to_repo)], "repository" + "."):
        try:
            out.append(importlib.import_module(name))
        except ImportError:
            # Ignore import errors - these will be detected by another unit test
            pass

    return out


def get_all_of_class_from_module(module, cls, exceptions=[]):
    out = []
    for obj_name in dir(module):
        obj = getattr(module, obj_name)
        if (
            inspect.isclass(obj)  # Is this a class
            and issubclass(obj, cls)  # ...of type cls?
            and obj.__module__ == module.__name__  # that was defined in this module
            and obj is not cls  # But not the cls class itself
            and obj.__name__[0] != "_"  # nor marked as private
            and obj not in exceptions  # nor one of the exceptions
        ):
            out.append(obj)
    return out


def get_all_of_class_from_repository(cls):
    out = []
    for module in get_all_repo_modules():
        env_experiments = get_all_of_class_from_module(
            module, cls, exceptions=[Calibration]
        )
        for exp in env_experiments:
            out.append((module, exp))
    return out


all_exp_fragments = get_all_of_class_from_repository(ExpFragment)


@pytest.mark.parametrize(
    "module, exp",
    all_exp_fragments,
    ids=[f"{module.__name__} / {exp.__name__}" for module, exp in all_exp_fragments],
)
def test_build_all_fragments(module, exp, fragment_precompiler):
    fragment_precompiler(exp)
