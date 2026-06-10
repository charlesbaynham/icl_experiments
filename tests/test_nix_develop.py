"""Tests that verify the nix develop shell works correctly."""

import subprocess as sp
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).parent.parent.resolve()


@pytest.mark.slow
def test_nix_develop_precommit_hooks_fire(tmp_path):
    """Clone the repo to a temp dir, modify a file, and verify pre-commit hooks fire.

    The pre-commit hooks are installed by the nix develop shellHook. We check
    that they actually run by looking for known hook names in the commit output.
    """
    clone_dir = tmp_path / "cloned_repo"

    sp.run(
        ["git", "clone", str(REPO_ROOT), str(clone_dir)],
        check=True,
        capture_output=True,
    )

    sp.run(
        ["git", "config", "user.email", "test@example.com"],
        cwd=clone_dir,
        check=True,
    )
    sp.run(
        ["git", "config", "user.name", "Test User"],
        cwd=clone_dir,
        check=True,
    )

    readme = clone_dir / "readme.rst"
    readme.write_text(readme.read_text() + "\n# test append\n")

    result = sp.run(
        ["nix", "develop", "-c", "git", "commit", "-am", "test"],
        cwd=clone_dir,
        capture_output=True,
        text=True,
        timeout=300,
    )

    combined = result.stdout + result.stderr
    hook_indicators = [
        "alejandra",
        "black",
        "autoflake",
        "isort",
        "prettier",
        "pre-commit",
    ]
    assert any(
        indicator in combined.lower() for indicator in hook_indicators
    ), f"Expected pre-commit hooks to fire, but none found in output:\n{combined}"


@pytest.mark.slow
def test_nix_develop_can_import_artiq():
    """Verify `python -c 'import artiq'` succeeds inside `nix develop`."""
    result = sp.run(
        ["nix", "develop", "-c", "python", "-c", "import artiq"],
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
        timeout=300,
    )
    assert result.returncode == 0, (
        f"Expected `import artiq` to succeed, but got rc={result.returncode}.\n"
        f"stdout: {result.stdout}\nstderr: {result.stderr}"
    )
