# import importlib
# import inspect
# import pkgutil
# from pathlib import Path

# import pytest
# from ndscan.experiment import ExpFragment
# from qbutler.calibration import Calibration

# path_to_repo = Path(__file__, "../../repository").resolve()


# def get_all_repo_modules():
#     return [
#         importlib.import_module(name)
#         for _, name, _ in pkgutil.walk_packages([str(path_to_repo)], "repository" + ".")
#     ]


# def get_all_of_class_from_module(module, cls, exceptions=[]):
#     out = []
#     for obj_name in dir(module):
#         obj = getattr(module, obj_name)
#         if (
#             inspect.isclass(obj)
#             and issubclass(obj, cls)  # Is this a cls?
#             and obj is not cls  # But not the cls class itself
#             and obj.__name__[0] != "_"  # nor marked as private
#             and obj not in exceptions  # nor one of the exceptions
#         ):
#             out.append(obj)
#     return out


# def get_all_of_class_from_repository(cls):
#     out = []
#     for module in get_all_repo_modules():
#         env_experiments = get_all_of_class_from_module(
#             module, cls, exceptions=[Calibration]
#         )
#         for exp in env_experiments:
#             out.append((module, exp))
#     return out


# all_exp_fragments = get_all_of_class_from_repository(ExpFragment)


# @pytest.mark.parametrize(
#     "module, exp",
#     all_exp_fragments,
#     ids=[f"{module.__name__} / {exp.__name__}" for module, exp in all_exp_fragments],
# )
# def test_build_all_fragments(module, exp, fragment_precompiler):
#     fragment_precompiler(exp)
