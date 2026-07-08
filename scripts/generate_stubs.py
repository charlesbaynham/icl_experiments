#!/usr/bin/env python3
"""Regenerate the ``stubs`` branch from one or more source branches.

The ``stubs`` branch is a drastically simplified mirror of the real
experiment repository: it contains no library code and no Nix packaging,
only a lightweight ``_Stub`` stand-in for every ARTIQ experiment that the
dashboard would discover on the source branch(es).

For every experiment on every source branch we emit a class that

* has the **same name** the ARTIQ explorer would show it under, and
* carries the **same docstring** (so the explorer displays the same
  description),

but whose body is the do-nothing :class:`repository.stub_experiment._Stub`.

The generated set is the **union** of the experiments found across all the
requested branches, so a single stubs branch can advertise experiments that
live on several feature branches at once.

Usage
-----
    # regenerate this working tree's stubs from master
    nix run .#generate_stubs -- --branches master

    # union of several branches (earlier branches win doc conflicts)
    nix run .#generate_stubs -- --branches master feature/a feature/b

    # inspect what would change without touching the tree
    nix run .#generate_stubs -- --branches master --dry-run

The script only reads the source branches through ``git`` (it never checks
them out) and writes the result into ``--output-dir`` (the current
directory by default), which is expected to be a checkout of the stubs
branch. Everything under ``repository/`` in the output directory that the
script manages is rewritten from scratch on every run.
"""

import argparse
import ast
import os
import subprocess
import sys
from dataclasses import dataclass
from dataclasses import field

# --- experiment classification -------------------------------------------

# A top-level class becomes a discoverable ARTIQ experiment iff its base
# chain reaches one of these roots. ``Calibration`` (qbutler) and
# ``FragmentScanExperiment`` (ndscan) are external experiment bases we
# cannot follow statically, so we treat them as roots by name.
EXP_ROOTS = {
    "EnvExperiment",
    "Experiment",
    "FragmentScanExperiment",
}
# ...and these are the (disjoint) fragment roots: a class that reaches one
# of these is a Fragment, which is only an experiment once wrapped in
# ``make_fragment_scan_exp``.
FRAG_ROOTS = {"ExpFragment", "Fragment"}

STUB_BASE_MODULE = "repository.stub_experiment"

GENERATED_HEADER = (
    '"""AUTO-GENERATED stub file - do not edit by hand.\n\n'
    "To regenerate see ``nix run .#generate_stubs -- --help``. Every class here mirrors\n"
    "the name and docstring of a real experiment on a source branch; the\n"
    "body is a no-op stub so the ARTIQ explorer can list it without any of\n"
    'the real dependencies.\n"""\n'
)


def _base_name(node: ast.expr) -> str | None:
    if isinstance(node, ast.Name):
        return node.id
    if isinstance(node, ast.Attribute):
        return node.attr
    return None


@dataclass
class Experiment:
    """One discoverable experiment: the name + docstring the explorer shows."""

    name: str
    docstring: str | None
    source_branch: str
    source_path: str


@dataclass
class TreeIndex:
    """Parsed view of a single branch's ``repository/`` tree."""

    # simple class name -> list of (path, base names, docstring)
    classes: dict[str, list[tuple[str, list[str | None], str | None]]] = field(
        default_factory=dict
    )
    # (path, target var, fragment class name) for make_fragment_scan_exp calls
    scan_exps: list[tuple[str, str, str | None]] = field(default_factory=list)

    def kind_of(self, name: str, _seen: set[str] | None = None) -> str:
        """Return 'exp', 'frag' or 'unknown' for a class name."""
        if _seen is None:
            _seen = set()
        if name in EXP_ROOTS:
            return "exp"
        if name in FRAG_ROOTS:
            return "frag"
        if name in _seen or name not in self.classes:
            return "unknown"
        _seen.add(name)
        for _, bases, _doc in self.classes[name]:
            for base in bases:
                if base is None:
                    continue
                kind = self.kind_of(base, _seen)
                if kind != "unknown":
                    return kind
        return "unknown"

    def docstring_of(self, name: str) -> str | None:
        for _, _bases, doc in self.classes.get(name, []):
            if doc:
                return doc
        return None


# --- git plumbing ---------------------------------------------------------


def _git(*args: str) -> str:
    return subprocess.run(
        ["git", *args], check=True, capture_output=True, text=True
    ).stdout


def branch_python_files(branch: str) -> dict[str, str]:
    """Return {path: source} for every repository/**.py file on ``branch``."""
    listing = _git("ls-tree", "-r", "--name-only", branch, "--", "repository")
    out: dict[str, str] = {}
    for path in listing.splitlines():
        if path.endswith(".py"):
            out[path] = _git("show", f"{branch}:{path}")
    return out


# --- enumeration ----------------------------------------------------------


def index_tree(sources: dict[str, str]) -> TreeIndex:
    index = TreeIndex()
    for path, src in sources.items():
        try:
            tree = ast.parse(src)
        except SyntaxError as exc:  # pragma: no cover - defensive
            print(f"  ! skipping unparseable {path}: {exc}", file=sys.stderr)
            continue
        for node in tree.body:
            if isinstance(node, ast.ClassDef):
                bases = [_base_name(b) for b in node.bases]
                doc = ast.get_docstring(node)
                index.classes.setdefault(node.name, []).append((path, bases, doc))
            elif isinstance(node, ast.Assign):
                value = node.value
                if (
                    isinstance(value, ast.Call)
                    and _base_name(value.func) == "make_fragment_scan_exp"
                ):
                    frag = _base_name(value.args[0]) if value.args else None
                    for target in node.targets:
                        if isinstance(target, ast.Name):
                            index.scan_exps.append((path, target.id, frag))
    return index


def enumerate_experiments(branch: str, sources: dict[str, str]) -> list[Experiment]:
    """All experiments the ARTIQ explorer would discover on this branch."""
    index = index_tree(sources)
    found: list[Experiment] = []

    # 1) ndscan: X = make_fragment_scan_exp(FragClass)
    # make_fragment_scan_exp copies the fragment's __name__ onto the shim, and
    # ARTIQ's is_public_experiment tests that __name__ - so publicness keys on
    # the fragment name, while the explorer lists it under the target var name.
    for path, target, frag in index.scan_exps:
        if frag and frag.startswith("_"):
            continue  # non-public experiment
        doc = index.docstring_of(frag) if frag else None
        found.append(Experiment(target, doc, branch, path))

    # 2) raw experiment classes (raw ARTIQ, Calibration monitors, _Stub, ...)
    for path, src in sources.items():
        for node in ast.parse(src).body:
            if not isinstance(node, ast.ClassDef):
                continue
            if node.name.startswith("_"):
                continue  # is_public_experiment filters underscore names
            if index.kind_of(node.name) == "exp":
                doc = ast.get_docstring(node)
                found.append(Experiment(node.name, doc, branch, path))
    return found


# --- output ---------------------------------------------------------------


def _indent_docstring(doc: str) -> str:
    # ``doc`` is already dedented by ast.get_docstring(); re-indent to 4 spaces.
    lines = doc.strip("\n").splitlines()
    body = "\n".join(("    " + ln).rstrip() for ln in lines)
    return f'    """\n{body}\n    """\n'


def render_stub_file(experiments: list[Experiment]) -> str:
    parts = [GENERATED_HEADER, f"\nfrom {STUB_BASE_MODULE} import _Stub\n"]
    for exp in experiments:
        parts.append(f"\n\nclass {exp.name}(_Stub):\n")
        if exp.docstring and exp.docstring.strip():
            parts.append(_indent_docstring(exp.docstring))
        else:
            parts.append("    pass\n")
    return "".join(parts)


STUB_BASE_SOURCE = '''"""Base class for auto-generated experiment stubs.

This is the only hand-written module on the stubs branch. ``_Stub`` is a
minimal ARTIQ experiment whose name starts with an underscore so the
explorer never lists it directly; every generated stub subclasses it.
"""

from artiq.experiment import EnvExperiment


class _Stub(EnvExperiment):
    def build(self):
        pass

    def run(self):
        raise NotImplementedError("""
This is a stub experiment!

To run this, you must provide a branch in the ref. If in doubt, use "master"
        """.strip())
'''


def build_output(
    branches: list[str],
) -> tuple[dict[str, list[Experiment]], list[str]]:
    """Return {output_path: [experiments]} plus a list of warnings."""
    by_path: dict[str, dict[str, Experiment]] = {}
    warnings: list[str] = []
    # source_path -> output_path, to detect collisions from lib-stripping
    out_to_src: dict[str, str] = {}

    for branch in branches:
        sources = branch_python_files(branch)
        for exp in enumerate_experiments(branch, sources):
            out_path = exp.source_path
            prior_src = out_to_src.setdefault(out_path, exp.source_path)
            if prior_src != exp.source_path:
                warnings.append(
                    f"path collision: {exp.source_path} and {prior_src} "
                    f"both map to {out_path}"
                )
            slot = by_path.setdefault(out_path, {})
            if exp.name in slot:
                existing = slot[exp.name]
                if (existing.docstring or "") != (exp.docstring or ""):
                    warnings.append(
                        f"{out_path}:{exp.name} docstring differs between "
                        f"{existing.source_branch} and {branch}; "
                        f"keeping {existing.source_branch}"
                    )
                continue  # earlier branch wins
            slot[exp.name] = exp

    ordered = {
        path: sorted(exps.values(), key=lambda e: e.name)
        for path, exps in sorted(by_path.items())
    }
    return ordered, warnings


def managed_repository_files(output_dir: str) -> set[str]:
    """Existing files under output_dir/repository (relative paths)."""
    root = os.path.join(output_dir, "repository")
    found: set[str] = set()
    for dirpath, _dirs, filenames in os.walk(root):
        for fn in filenames:
            if fn.endswith(".py"):
                rel = os.path.relpath(os.path.join(dirpath, fn), output_dir)
                found.add(rel)
    return found


def write_output(
    output_dir: str,
    by_path: dict[str, list[Experiment]],
    dry_run: bool,
) -> None:
    wanted: dict[str, str] = {}
    wanted["repository/stub_experiment.py"] = STUB_BASE_SOURCE
    for out_path, exps in by_path.items():
        wanted[out_path] = render_stub_file(exps)

    # Ensure every directory from repository/ down is a package.
    package_dirs: set[str] = set()
    for out_path in wanted:
        d = os.path.dirname(out_path)
        while d and d != ".":
            package_dirs.add(d)
            d = os.path.dirname(d)
    for d in package_dirs:
        wanted.setdefault(f"{d}/__init__.py", "")

    existing = managed_repository_files(output_dir)
    obsolete = existing - set(wanted)

    print(
        f"stub files: {sum(1 for p in wanted if p.endswith('.py') and '__init__' not in p) - 1}"
    )
    print(f"experiments: {sum(len(v) for v in by_path.values())}")
    print(f"files to write: {len(wanted)}   obsolete to remove: {len(obsolete)}")

    if dry_run:
        for path in sorted(obsolete):
            print(f"  - would remove {path}")
        return

    for path in sorted(obsolete):
        os.remove(os.path.join(output_dir, path))
    # prune now-empty dirs
    for dirpath, _dirs, filenames in os.walk(
        os.path.join(output_dir, "repository"), topdown=False
    ):
        if not os.listdir(dirpath):
            os.rmdir(dirpath)

    for path, content in wanted.items():
        full = os.path.join(output_dir, path)
        os.makedirs(os.path.dirname(full), exist_ok=True)
        with open(full, "w") as fh:
            fh.write(content)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--branches",
        nargs="+",
        default=["master"],
        help="Source branches; earlier branches win docstring conflicts.",
    )
    parser.add_argument(
        "--output-dir",
        default=".",
        help="Checkout of the stubs branch to write into (default: cwd).",
    )
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()

    by_path, warnings = build_output(args.branches)
    write_output(args.output_dir, by_path, args.dry_run)

    for w in warnings:
        print(f"  warning: {w}", file=sys.stderr)
    if any(w.startswith("path collision") for w in warnings):
        print("ERROR: path collisions detected; aborting.", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
