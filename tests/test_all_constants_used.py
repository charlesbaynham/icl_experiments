import ast
from pathlib import Path

from repository.lib import constants


def find_used_constants_in_file(file_path, constant_names):
    file_path = Path(file_path)
    tree = ast.parse(file_path.read_text(), filename=str(file_path))

    used_constants = set()

    class ConstantVisitor(ast.NodeVisitor):
        def visit_Name(self, node):
            if node.id in constant_names:
                used_constants.add(node.id)

    ConstantVisitor().visit(tree)
    return used_constants


def test_constants_usage():
    # Get all the constant names from constants.py
    constant_names = [
        name for name in dir(constants) if name.isupper() and not name.startswith("__")
    ]

    if not constant_names:
        raise AssertionError("No constants found in constants.py")

    used_constants = set()

    # Directory to search through
    search_dir = Path(__file__).parent.parent

    for file_path in search_dir.rglob("*.py"):
        if file_path.name not in ("constants.py", "test_constants_usage.py"):
            used_constants.update(
                find_used_constants_in_file(file_path, constant_names)
            )

    unused_constants = set(constant_names) - used_constants

    assert not unused_constants, f"Unused constants detected: {unused_constants}"
