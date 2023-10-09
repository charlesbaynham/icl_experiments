import importlib
from artiq.language.environment import is_public_experiment
from ndscan.experiment import ExpFragment
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
        if inspect.isclass(obj) and issubclass(obj, cls) and obj is not cls:
            out.append(obj)
    return out


def get_all_of_class_from_repository(cls):
    out = []
    for module in get_all_repo_modules():
        env_experiments = get_all_of_class_from_module(module, cls)
        for exp in env_experiments:
            out.append((module, exp))
    return out


# all_env_experiments = get_all_of_class_from_repository(EnvExperiment)
all_exp_fragments = get_all_of_class_from_repository(ExpFragment)

# all_env_experiments = all_env_experiments[0:1]
# all_exp_fragments = all_exp_fragments[0:1]

from repository.measure_red_mot import _BroadbandBase

all_exp_fragments = [(None, _BroadbandBase)]


@pytest.mark.parametrize(
    "module, exp",
    all_exp_fragments,
    ids=[exp for _, exp in all_exp_fragments],
)
def test_build_all_fragments(module, exp, fragment_factory):
    def precompile(self):
        precompiled_setup = self.core.precompile(self.device_setup)
        precompiled_run = self.core.precompile(self.run_once)
        precompiled_cleanup = self.core.precompile(self.device_cleanup)

        print("Experiment was precompiled:")
        print(precompiled_setup)
        print(precompiled_run)
        print(precompiled_cleanup)

    setattr(exp, "precompile", precompile)

    exp_built = fragment_factory(exp)

    if not hasattr(exp_built, "core"):
        return  # This Fragment has no kernel code

    exp_built.host_setup()
    exp_built.precompile()


# @pytest.mark.parametrize(
#     "module, exp",
#     all_env_experiments,
#     ids=[exp for _, exp in all_env_experiments],
# )
# def test_all_fragments_compile(module, exp, fragment_factory):
#     def precompile(self):
#         precompiled_setup = self.core.precompile(self.device_setup)
#         precompiled_run = self.core.precompile(self.run_once)
#         precompiled_cleanup = self.core.precompile(self.device_cleanup)
#         print("Experiment was precompiled:")
#         print(precompiled_setup)
#         print(precompiled_run)
#         print(precompiled_cleanup)
#     setattr(MeasureRedMOTFrag, "precompile", precompile)
#     exp = fragment_factory(MeasureRedMOTFrag)
#     exp.precompile()
#     experiment_factory(exp)
