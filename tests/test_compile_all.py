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


def get_all_envexperiments_from_module(module):
    out = []
    for obj_name in dir(module):
        obj = getattr(module, obj_name)
        if inspect.isclass(obj) and issubclass(obj, EnvExperiment):
            out.append(obj)
    return out


def get_all_envExperiments():
    out = []
    for module in get_all_repo_modules():
        env_experiments = get_all_envexperiments_from_module(module)
        for exp in env_experiments:
            out.append((module, exp))

    return out


@pytest.mark.parametrize(
    "module, exp",
    get_all_envExperiments(),
    ids=[exp for _, exp in get_all_envExperiments()],
)
def test_build_all_experiments(module, exp, experiment_factory):
    experiment_factory(exp)
