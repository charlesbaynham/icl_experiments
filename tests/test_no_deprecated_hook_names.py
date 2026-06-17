"""
Test that deprecated experiment lifecycle hook names are no longer used.

Seven lifecycle hooks were converted to the checkpoint system (see
``repository/lib/fragments/checkpoint_fragment.py`` and the
``RedMOTCheckpoints.checkpoint_method_names`` list). Their old ``*_hook``
names -- and the ``*_hook_<suffix>`` helper methods that cascaded from them --
are deprecated and should now use the ``*_checkpoint`` equivalents instead.

This test greps the repository's Python source for the deprecated names and
fails if any remain, so that stragglers can be migrated. It deliberately does
*not* fix anything: it only detects.

Note: ``post_narrowband_hook`` and ``host_functions_after_experiment_hook``
were intentionally *kept* as hooks (their defaults still carry behaviour), so
they are not listed here.
"""

import os
import re
from pathlib import Path
from typing import Dict
from typing import List
from typing import Tuple

import pytest

# Mapping of deprecated lifecycle hook base names to the checkpoint that
# replaced them. Any identifier that starts with one of these base names (e.g.
# the hook itself, or a ``*_hook_default`` / ``*_hook_base`` helper) is
# considered deprecated.
DEPRECATED_HOOK_TO_CHECKPOINT: Dict[str, str] = {
    "DMA_initialization_hook": "DMA_initialization_checkpoint",
    "pre_sequence_hook": "pre_sequence_checkpoint",
    "end_of_blue_3d_mot_loading_hook": "end_of_blue_3d_mot_loading_checkpoint",
    "start_of_red_broadband_hook": "start_of_red_broadband_checkpoint",
    "end_of_broadband_mot_hook": "end_of_broadband_mot_checkpoint",
    "pre_expansion_hook": "pre_expansion_checkpoint",
    "post_sequence_cleanup_hook": "post_sequence_cleanup_checkpoint",
}

# A single regex matching any deprecated hook base name. ``re.escape`` keeps it
# robust if a future name contains regex metacharacters. We match the base name
# followed by anything that is *not* a continuation that would make it a
# different, unrelated identifier -- in practice the base names are unique
# enough that a plain substring search is correct, but we anchor the start on a
# word boundary so we don't match inside a longer prefix.
_DEPRECATED_PATTERN = re.compile(
    r"\b(" + "|".join(re.escape(name) for name in DEPRECATED_HOOK_TO_CHECKPOINT) + r")"
)

# Directories that are not part of the project's own production source and so
# should not be scanned: third-party vendored code, caches, virtualenvs, and
# the test suite itself (this file necessarily mentions the deprecated names).
_EXCLUDED_DIRS = {
    "vendor",
    "tests",
    "__pycache__",
    ".git",
    ".venv",
    ".tox",
    "node_modules",
}


def _repo_root() -> Path:
    """Return the repository root (the parent of this ``tests`` directory)."""
    return Path(__file__).resolve().parent.parent


def _python_source_files(root: Path) -> List[Path]:
    """Yield all project Python files, skipping excluded directories."""
    python_files: List[Path] = []
    for dirpath, dirnames, filenames in os.walk(root):
        # Prune excluded directories in place so os.walk doesn't descend them.
        dirnames[:] = [d for d in dirnames if d not in _EXCLUDED_DIRS]
        for filename in filenames:
            if filename.endswith(".py"):
                python_files.append(Path(dirpath) / filename)
    return python_files


def _find_deprecated_usages(root: Path) -> List[Tuple[Path, int, str, str]]:
    """
    Scan all project Python files for deprecated hook names.

    Returns a list of ``(path, line_number, deprecated_name, line_text)``
    tuples, one per matching line.
    """
    findings: List[Tuple[Path, int, str, str]] = []
    for path in _python_source_files(root):
        try:
            text = path.read_text(encoding="utf-8")
        except (UnicodeDecodeError, OSError):
            continue
        for lineno, line in enumerate(text.splitlines(), start=1):
            match = _DEPRECATED_PATTERN.search(line)
            if match:
                findings.append((path, lineno, match.group(1), line.strip()))
    return findings


def test_no_deprecated_hook_names():
    """
    Fail if any deprecated lifecycle hook name still appears in project source.

    Each finding lists the location and the checkpoint that should be used
    instead. This test only detects deprecated usages; migrating them is left
    to a follow-up change.
    """
    root = _repo_root()
    findings = _find_deprecated_usages(root)

    if findings:
        lines = [
            f"Found {len(findings)} usage(s) of deprecated lifecycle hook names. "
            "These were converted to the checkpoint system and should be "
            "migrated to their *_checkpoint equivalents:\n"
        ]
        for path, lineno, name, text in findings:
            replacement = DEPRECATED_HOOK_TO_CHECKPOINT[name]
            rel = os.path.relpath(path, root)
            lines.append(f"  {rel}:{lineno}: {name} -> use {replacement}")
            lines.append(f"      {text}")

        pytest.fail("\n".join(lines))
