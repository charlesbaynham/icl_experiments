"""Guard against ``from __future__ import annotations`` in the experiment code.

PEP 563 turns every annotation into a string. When ARTIQ's master examines the
repository it imports each module via ``artiq.tools.file_import``, which execs
the module **without** registering it in ``sys.modules``. On Python 3.10 the
``@dataclass`` machinery then tries to resolve a bare-name string annotation
with ``sys.modules.get(cls.__module__).__dict__``; the module is absent, so this
returns ``None`` and raises ``AttributeError: 'NoneType' object has no attribute
'__dict__'``. The master logs an error and silently skips the file, so the
affected experiments disappear from the dashboard.

The fix is simply not to use the future import: our annotations are all
runtime-evaluatable, so real annotation objects work fine and avoid the
string-resolution code path entirely. This test keeps it from creeping back in.
"""

import ast
from pathlib import Path

import dedrifter
import repository

# Packages whose modules get imported by the ARTIQ master's examine pass.
SEARCH_DIRS = [
    Path(repository.__file__).parent,
    Path(dedrifter.__file__).parent,
]


def _uses_future_annotations(path: Path) -> bool:
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    for node in tree.body:
        if isinstance(node, ast.ImportFrom) and node.module == "__future__":
            if any(alias.name == "annotations" for alias in node.names):
                return True
    return False


def test_no_future_annotations_import():
    """No module under repository/ or dedrifter/ may use PEP 563 annotations."""
    offenders = [
        str(f)
        for search_dir in SEARCH_DIRS
        for f in search_dir.rglob("*.py")
        if _uses_future_annotations(f)
    ]

    assert not offenders, (
        "`from __future__ import annotations` breaks ARTIQ examine for modules "
        "defining dataclasses (see this file's docstring). Remove it from:\n"
        + "\n".join(f"  - {f}" for f in sorted(offenders))
    )
