import ast
import os

# Assuming the constants are defined in a file named `constants.py`
CONSTANTS_FILE = (
    "/home/stronlab/artiq_stuff/icl_experiments/repository/lib/constants.py"
)
CODE_DIRECTORY = "/home/stronlab/artiq_stuff/icl_experiments"


def get_defined_constants(file_path):
    """Extract all top-level variables defined in the constants file."""
    with open(file_path, "r") as f:
        tree = ast.parse(f.read(), filename=file_path)
    return {node.targets[0].id for node in tree.body if isinstance(node, ast.Assign)}


def is_constant_used(constant, code_directory):
    """Check if a constant is used in any Python file in the code directory."""
    for root, _, files in os.walk(code_directory):
        for file in files:
            if file.endswith(".py") and file != os.path.basename(CONSTANTS_FILE):
                file_path = os.path.join(root, file)
                with open(file_path, "r") as f:
                    if constant in f.read():
                        return True
    return False


def test_all_constants_used():
    """Test to ensure all constants are used somewhere in the code."""
    constants = get_defined_constants(CONSTANTS_FILE)
    unused_constants = [
        const for const in constants if not is_constant_used(const, CODE_DIRECTORY)
    ]
    assert (
        not unused_constants
    ), f"The following constants are unused: {unused_constants}"
