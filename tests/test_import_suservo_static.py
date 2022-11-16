from pathlib import Path

from artiq import tools
from artiq.experiment import Experiment
from artiq.language.environment import is_public_experiment

SUSERVO_FILE = str(Path(__file__, "../../repository/set_suservo_static.py").resolve())
SUSERVO_CLASS = "SetSUServoStaticExp"


def test_static_suservo_is_public_experiment():
    module = tools.file_import(SUSERVO_FILE)
    expclass = getattr(module, SUSERVO_CLASS)

    assert is_public_experiment(expclass)


def test_static_suservo_is_subclass_experiment():
    module = tools.file_import(SUSERVO_FILE)
    expclass = getattr(module, SUSERVO_CLASS)

    assert issubclass(expclass, Experiment)
