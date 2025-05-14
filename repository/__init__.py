import importlib
import logging
import sys

logger = logging.getLogger(__name__)

# Use this list to override pyaion modules with local ones.
# by passing the name of the pyaion module you want to override. It will be
# replaced by the module of the same name in "lib.fragments.pyaion_overrides"
pyaion_override_list = [
    "pyaion.fragments.toggle_beams_with_AOM_and_shutter",  # FIXME
]


for override_name in pyaion_override_list:
    pyaion_module = importlib.import_module(override_name)
    local_module = importlib.import_module(
        "repository.lib.fragments.pyaion_overrides." + override_name.split(".")[-1]
    )

    sys.modules[override_name] = local_module

    logger.warning("Overriding pyaion module '%s' with local copy", override_name)
