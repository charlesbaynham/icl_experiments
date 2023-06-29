import importlib
import inspect
import pkgutil
from pathlib import Path

import pytest
from artiq.experiment import EnvExperiment

path_to_repo = Path(__file__, "../../repository").resolve()


def get_all_repo_modules():
    return [
        importlib.import_module(name)
        for _, name, _ in pkgutil.walk_packages([str(path_to_repo)], "repository" + ".")
    ]


def get_all_of_class_from_module(module, cls):
    out = []
    for obj_name in dir(module):
        obj = getattr(module, obj_name)
        if inspect.isclass(obj) and issubclass(obj, cls):
            out.append(obj)
    return out


def get_all_of_class_from_repository(cls):
    out = []
    for module in get_all_repo_modules():
        env_experiments = get_all_of_class_from_module(module, cls)
        for exp in env_experiments:
            out.append((module, exp))

    return out


all_env_experiments = get_all_of_class_from_repository(EnvExperiment)


@pytest.mark.parametrize(
    "module, exp",
    all_env_experiments,
    ids=[exp for _, exp in all_env_experiments],
)
def test_build_all_experiments(module, exp, experiment_factory):
    experiment_factory(exp)
