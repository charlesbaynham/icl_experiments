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
            and not obj.__name__.endswith(
                "Base"
            )  # nor ends in "Base" and is therefore allowed to be abstract
            and not obj.__name__.endswith(
                "Mixin"
            )  # nor ends in "Mixin" and is therefore allowed to be abstract
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

# Add xfailing modules. Each entry is (name_substring, reason, strict); strict
# defaults to the project-wide xfail_strict=true, but flaky failures must use
# strict=False so that an unexpected pass (XPASS) does not fail the run.
xfails = [
    # ("ScanTopticaMOTFrag", "Toptica host setup is not mocked")
    # ("ScanKoheronMeasureScopeFrag", "pipeline can't talk to scope")
    (
        "MeasureXODTNewMolassesFrag",
        "general_setter_names length mismatch in pyaion/fragments/ramping_phase.py",
        True,
    ),
    (
        "TestMatterwaveCollimationInDipoleTrapFrag",
        "host object does not have an attribute 'dds'",
        True,
    ),
]

xfail_names = [x[0] for x in xfails]
all_exp_fragments_marked = []

for module, exp in all_exp_fragments:
    if any((name in exp.__name__ for name in xfail_names)):
        for xfail_name, xfail_reason, xfail_strict in xfails:
            if xfail_name in exp.__name__:
                all_exp_fragments_marked.append(
                    pytest.param(
                        module,
                        exp,
                        marks=pytest.mark.xfail(
                            reason=xfail_reason, strict=xfail_strict
                        ),
                    ),
                )
                break
    else:
        all_exp_fragments_marked.append((module, exp))


@pytest.mark.parametrize(
    "module, exp",
    all_exp_fragments_marked,
    ids=[f"{module.__name__} / {exp.__name__}" for module, exp in all_exp_fragments],
)
def test_build_all_fragments(module, exp, fragment_precompiler):
    fragment_precompiler(exp)
