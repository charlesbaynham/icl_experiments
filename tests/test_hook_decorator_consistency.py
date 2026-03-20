"""
Test to validate decorator consistency in ARTIQ experiment hook method overrides.

This test discovers all ARTIQ experiment classes, finds hook method overrides
(methods matching xxx_yyy_hook pattern), and checks that the decorator matches
the base class definition.
"""

import ast
import os
import re
from pathlib import Path
from typing import Dict
from typing import List
from typing import Optional
from typing import Set
from typing import Tuple

import pytest


def get_decorator_name(decorator_node) -> Optional[str]:
    """Extract the name of a decorator from an AST node."""
    if isinstance(decorator_node, ast.Name):
        return decorator_node.id
    elif isinstance(decorator_node, ast.Call):
        if isinstance(decorator_node.func, ast.Name):
            return decorator_node.func.id
        elif isinstance(decorator_node.func, ast.Attribute):
            return decorator_node.func.attr
    elif isinstance(decorator_node, ast.Attribute):
        return decorator_node.attr
    return None


def get_decorator_with_args(decorator_node) -> Tuple[Optional[str], Optional[str]]:
    """
    Extract the decorator name and any arguments.
    Returns (name, args_str) where args_str is a string representation of arguments.
    """
    if isinstance(decorator_node, ast.Name):
        return decorator_node.id, None
    elif isinstance(decorator_node, ast.Call):
        if isinstance(decorator_node.func, ast.Name):
            name = decorator_node.func.id
        elif isinstance(decorator_node.func, ast.Attribute):
            name = decorator_node.func.attr
        else:
            return None, None

        # Try to get a simple string representation of arguments
        args_str = (
            ast.unparse(decorator_node.args)
            if hasattr(ast, "unparse") and decorator_node.args
            else "..."
        )
        return name, args_str
    elif isinstance(decorator_node, ast.Attribute):
        return decorator_node.attr, None
    return None, None


class HookMethodInfo:
    """Information about a hook method found in a class."""

    def __init__(
        self,
        class_name: str,
        method_name: str,
        decorators: List[Tuple[str, Optional[str]]],
    ):
        self.class_name = class_name
        self.method_name = method_name
        self.decorators = decorators  # List of (decorator_name, args_str)

    def get_artiq_decorator(self) -> Optional[Tuple[str, Optional[str]]]:
        """Get the ARTIQ decorator (@kernel, @rpc, @subkernel, @host_only) if present."""
        for name, args in self.decorators:
            if name in ("kernel", "rpc", "subkernel", "host_only"):
                return (name, args)
        return None

    def __repr__(self):
        return f"HookMethodInfo({self.class_name}.{self.method_name}, decorators={self.decorators})"


def find_hook_methods_in_file(filepath: Path) -> List[HookMethodInfo]:
    """
    Parse a Python file and find all hook methods with their decorators.

    Hook methods are defined as methods matching the pattern: xxx_yyy_hook
    """
    hook_methods = []

    try:
        with open(filepath, "r", encoding="utf-8") as f:
            source = f.read()

        tree = ast.parse(source)
    except (SyntaxError, UnicodeDecodeError, FileNotFoundError) as e:
        return hook_methods

    for node in ast.walk(tree):
        if isinstance(node, ast.ClassDef):
            class_name = node.name

            for item in node.body:
                if isinstance(item, ast.FunctionDef):
                    method_name = item.name

                    # Check if this is a hook method (matches xxx_yyy_hook pattern)
                    # Pattern: something ending in _hook but not _hook_default or _hook_base
                    if re.match(r"^[a-zA-Z_][a-zA-Z0-9_]*_hook$", method_name):
                        decorators = []
                        for decorator in item.decorator_list:
                            dec_name, dec_args = get_decorator_with_args(decorator)
                            if dec_name:
                                decorators.append((dec_name, dec_args))

                        hook_methods.append(
                            HookMethodInfo(
                                class_name=class_name,
                                method_name=method_name,
                                decorators=decorators,
                            )
                        )

    return hook_methods


def build_class_hierarchy(filepath: Path) -> Dict[str, Optional[str]]:
    """Build a map of class names to their base class names from a file."""
    class_bases = {}

    try:
        with open(filepath, "r", encoding="utf-8") as f:
            source = f.read()

        tree = ast.parse(source)
    except (SyntaxError, UnicodeDecodeError, FileNotFoundError):
        return class_bases

    for node in ast.walk(tree):
        if isinstance(node, ast.ClassDef):
            class_name = node.name

            # Get the first base class name (if any)
            if node.bases:
                base = node.bases[0]
                if isinstance(base, ast.Name):
                    class_bases[class_name] = base.id
                elif isinstance(base, ast.Attribute):
                    # module.ClassName
                    class_bases[class_name] = base.attr
                else:
                    class_bases[class_name] = None
            else:
                class_bases[class_name] = None

    return class_bases


def get_all_python_files(repository_path: Path) -> List[Path]:
    """Get all Python files in the repository, excluding tests."""
    python_files = []

    for root, dirs, files in os.walk(repository_path):
        # Skip test directories
        dirs[:] = [
            d for d in dirs if d not in ("tests", "__pycache__", ".git", ".venv")
        ]

        for file in files:
            if file.endswith(".py") and not file.startswith("test_"):
                python_files.append(Path(root) / file)

    return python_files


def collect_all_hook_methods(repository_path: Path) -> Dict[str, List[HookMethodInfo]]:
    """
    Collect all hook methods from all Python files in the repository.

    Returns a dict mapping fully qualified class names to lists of HookMethodInfo.
    """
    all_hooks: Dict[str, List[HookMethodInfo]] = {}
    class_locations: Dict[str, Path] = {}

    python_files = get_all_python_files(repository_path)

    for filepath in python_files:
        # Get the module name from the file path
        relative_path = filepath.relative_to(repository_path.parent)
        module_parts = list(relative_path.with_suffix("").parts)

        hook_methods = find_hook_methods_in_file(filepath)

        for hook in hook_methods:
            # Create a fully qualified class name
            class_name = hook.class_name

            # Store the hook by class name
            if class_name not in all_hooks:
                all_hooks[class_name] = []
            all_hooks[class_name].append(hook)
            class_locations[class_name] = filepath

    return all_hooks, class_locations


def find_base_class_method(
    hook_name: str,
    class_name: str,
    class_to_hooks: Dict[str, List[HookMethodInfo]],
    class_hierarchy: Dict[str, Optional[str]],
    visited: Optional[Set[str]] = None,
) -> Optional[HookMethodInfo]:
    """
    Find the hook method definition in the base class hierarchy.

    Returns the HookMethodInfo from the first base class that defines this hook,
    or None if not found in any base class.
    """
    if visited is None:
        visited = set()

    if class_name in visited:
        return None
    visited.add(class_name)

    # Get the base class name
    base_name = class_hierarchy.get(class_name)
    if not base_name:
        return None

    # Check if the base class has this hook
    base_hooks = class_to_hooks.get(base_name, [])
    for hook in base_hooks:
        if hook.method_name == hook_name:
            return hook

    # Recursively check the base class's base class
    return find_base_class_method(
        hook_name, base_name, class_to_hooks, class_hierarchy, visited
    )


def check_decorator_consistency(repository_path: Path) -> List[str]:
    """
    Check decorator consistency across hook method overrides.

    Returns a list of error messages describing any inconsistencies found.
    """
    errors = []

    # Collect all hook methods from all files
    all_hooks, class_locations = collect_all_hook_methods(repository_path)

    # Build class hierarchy for each file
    class_hierarchy = {}
    python_files = get_all_python_files(repository_path)

    for filepath in python_files:
        file_hierarchy = build_class_hierarchy(filepath)
        class_hierarchy.update(file_hierarchy)

    # Check each class's hooks against base class definitions
    for class_name, hooks in all_hooks.items():
        for hook in hooks:
            # Find the base class definition of this hook
            base_hook = find_base_class_method(
                hook.method_name, class_name, all_hooks, class_hierarchy
            )

            if base_hook is None:
                # No base class definition found - this might be the first definition
                continue

            # Get decorators
            subclass_dec = hook.get_artiq_decorator()
            base_dec = base_hook.get_artiq_decorator()

            # Check if base has an ARTIQ decorator but subclass doesn't
            if base_dec is not None and subclass_dec is None:
                base_file = class_locations.get(base_hook.class_name, Path("unknown"))
                subclass_file = class_locations.get(hook.class_name, Path("unknown"))

                errors.append(
                    f"Decorator mismatch for {hook.method_name}: "
                    f"Base class '{base_hook.class_name}' has @{base_dec[0]} but "
                    f"subclass '{hook.class_name}' has no ARTIQ decorator\n"
                    f"  Base location: {base_file}:{base_hook.class_name}\n"
                    f"  Subclass location: {subclass_file}:{hook.class_name}"
                )
            # Check if decorators differ
            elif base_dec is not None and subclass_dec is not None:
                if base_dec[0] != subclass_dec[0]:
                    base_file = class_locations.get(
                        base_hook.class_name, Path("unknown")
                    )
                    subclass_file = class_locations.get(
                        hook.class_name, Path("unknown")
                    )

                    errors.append(
                        f"Decorator mismatch for {hook.method_name}: "
                        f"Base class '{base_hook.class_name}' has @{base_dec[0]} but "
                        f"subclass '{hook.class_name}' has @{subclass_dec[0]}\n"
                        f"  Base location: {base_file}:{base_hook.class_name}\n"
                        f"  Subclass location: {subclass_file}:{hook.class_name}"
                    )

    return errors


@pytest.fixture
def repository_path():
    """Get the path to the repository."""
    # Look for the repository in common locations
    possible_paths = [
        Path(__file__).parent.parent / "repository",
        Path.home() / "projects" / "imperial-experiments" / "repository",
        Path("/home/charles/projects/imperial-experiments/repository"),
    ]

    for path in possible_paths:
        if path.exists():
            return path

    # Default to the first option and let the test fail gracefully
    return possible_paths[0]


def test_hook_decorator_consistency(repository_path):
    """
    Test that hook method overrides have consistent decorators with their base classes.

    This test validates that when a subclass overrides a hook method from a base class,
    the decorator must match the base class's decorator. For example:

    - If base class has: @kernel def prepare_devices_hook(self):
    - Then subclass must have: @kernel def prepare_devices_hook(self):
    - Not: def prepare_devices_hook(self): (missing decorator) or
    - Not: @rpc def prepare_devices_hook(self): (wrong decorator)

    This is important because ARTIQ uses decorators to determine which execution
    context (kernel, RPC, subkernel) a method runs in, and mismatches can cause
    runtime errors or unexpected behavior.
    """
    errors = check_decorator_consistency(repository_path)

    if errors:
        error_message = "Found hook method decorator inconsistencies:\n\n"
        for i, error in enumerate(errors, 1):
            error_message += f"{i}. {error}\n\n"

        pytest.fail(error_message)
