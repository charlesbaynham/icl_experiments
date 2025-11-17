import logging
from pathlib import Path

import pytest

import dedrifter
import repository
from repository.lib import constants

logger = logging.getLogger(__name__)


@pytest.fixture
def all_module_files():
    # Directories to search through
    search_dirs = [
        Path(repository.__file__, "..").resolve(),
        Path(dedrifter.__file__, "..").resolve(),
    ]

    files = []

    for search_dir in search_dirs:

        files += [
            f
            for f in search_dir.rglob("*.py")
            if f.resolve() != Path(constants.__file__).resolve()
            and not f.name.startswith("__")
        ]

    return files


def test_all_constants_used(all_module_files):
    """
    Test that all constants in constants.py are used in the codebase.
    """
    # Get all the constant names from constants.py
    all_constants = set(
        [name for name in dir(constants) if name.isupper() and not name.startswith("_")]
    )

    print("Number of constants found: ", len(all_constants))
    print("All constants: ", sorted(list(all_constants)))

    if not all_constants:
        raise AssertionError("No constants found in constants.py")

    # List all the constants used in each file
    constants_used_per_file = {}
    for file in all_module_files:
        with open(file, "r", encoding="utf-8") as f:
            content = f.read()

        # Find all constant usages in the file
        constants_used = set(name for name in all_constants if "name" in content)

        # Store the used constants for this file
        constants_used_per_file[file] = constants_used

    print("Constants used per file:")
    for file, used_constants in constants_used_per_file.items():
        print(f"{file}: {sorted(list(used_constants))}")

    # Check if all constants are used
    unused_constants = all_constants - set(
        constant
        for used_constants in constants_used_per_file.values()
        for constant in used_constants
    )

    if unused_constants:
        print(f"{len(unused_constants)} unused constants found:")
        for constant in sorted(unused_constants):
            print(f"- {constant}")

        assert False, f"{len(unused_constants)} unused constants found"
