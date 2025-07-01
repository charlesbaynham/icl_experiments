import logging
import sys
from pathlib import Path

import pytest

import repository
from repository.lib import constants

logger = logging.getLogger(__name__)


@pytest.fixture
def mocked_constants():
    # Mock the constants module
    original_constants = constants
    accessed_constants = set()

    class NewConstants:
        def __getattr__(self, name):
            # Record getattr accesses
            accessed_constants.add(name)

            # Return the constant from the original module
            return getattr(original_constants, name)

    # Patch the constants module with the new one
    sys.modules["repository.lib.constants"] = NewConstants()

    # return a getter for the accessed constants
    def get_accessed_constants():
        return accessed_constants.copy()

    yield get_accessed_constants

    # Cleanup: restore the original constants module
    sys.modules["repository.lib.constants"] = original_constants


@pytest.fixture
def used_constants_by_file(mocked_constants):
    used_constants_by_file = {}

    # Directory to search through
    search_dir = Path(repository.__file__, "..").resolve()

    for file_path in search_dir.rglob("*.py"):
        if file_path.resolve() != Path(
            constants.__file__
        ).resolve() and not file_path.name.startswith("__"):
            # import the file
            import importlib

            # Convert file path to module name
            module_name = file_path.relative_to(search_dir).with_suffix("").as_posix()
            module_name = module_name.replace("/", ".")

            importlib.import_module(f"repository.{module_name}")

            # See what constants got used
            used_constants = mocked_constants()

            logger.debug(f"File {file_path} used constants: {used_constants}")

            used_constants_by_file[file_path] = used_constants

    return used_constants_by_file.copy()


def test_all_constants_used(used_constants_by_file):
    """
    Test that all constants in constants.py are used in the codebase.
    """
    # Get all the constant names from constants.py
    all_constants = set(
        [name for name in dir(constants) if name.isupper() and not name.startswith("_")]
    )

    print("Number of constants found: ", len(all_constants))
    print("All constants: ", sorted(list(all_constants)))

    print("Used constants by file:")
    for file_path, used_constants in used_constants_by_file.items():
        print(f"{file_path}: {sorted(list(used_constants))}")

    if not all_constants:
        raise AssertionError("No constants found in constants.py")

    # Check if any constants are unused
    unused_constants = all_constants.copy()
    for file_path, used_constants in used_constants_by_file.items():
        unused_constants -= used_constants

    if unused_constants:
        raise AssertionError(f"Unused constants: {unused_constants}")
