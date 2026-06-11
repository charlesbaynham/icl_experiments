"""Tests that verify the nix develop shell works correctly."""

import subprocess as sp
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).parent.parent.resolve()


HOOK_INDICATORS = [
    "alejandra",
    "black",
    "autoflake",
    "isort",
    "prettier",
    "end-of-file-fixer",
    "trim-trailing-whitespace",
]


def _clone_and_configure(src, dest):
    """Clone ``src`` to ``dest`` and set a committer identity."""
    sp.run(["git", "clone", str(src), str(dest)], check=True, capture_output=True)
    sp.run(["git", "config", "user.email", "test@example.com"], cwd=dest, check=True)
    sp.run(["git", "config", "user.name", "Test User"], cwd=dest, check=True)


def _assert_commit_succeeded(result):
    """Assert a `nix develop -c git commit` actually committed and hooks ran."""
    combined = result.stdout + result.stderr

    # The commit must SUCCEED. The previous version of this test only checked
    # that the output contained a word like "pre-commit" and ignored the return
    # code -- but the failure message ("InvalidConfigError ... Check the log at
    # .../pre-commit.log") contains "pre-commit" too, so it passed against a
    # completely broken hook. Check the return code and the error explicitly.
    assert result.returncode == 0, (
        f"Commit failed (rc={result.returncode}); pre-commit hook is broken.\n"
        f"{combined}"
    )
    assert (
        "invalidconfigerror" not in combined.lower()
    ), f"pre-commit rejected its own config (PYTHONPATH pollution?):\n{combined}"
    assert any(
        indicator in combined.lower() for indicator in HOOK_INDICATORS
    ), f"Expected pre-commit hooks to fire, but none found in output:\n{combined}"


@pytest.mark.slow
def test_nix_develop_fresh_clone_commit_succeeds(tmp_path):
    """A commit inside `nix develop` on a fresh clone must succeed.

    This is the basic case and it is the one that regressed: the artiq dev shell
    puts an *unpatched* pre-commit on PYTHONPATH, which shadows the patched
    modules when the git hook runs, so every commit died with
    ``InvalidConfigError: ... language: 'unsupported'`` -- even on a clean
    checkout with a freshly installed hook.
    """
    clone_dir = tmp_path / "cloned_repo"
    _clone_and_configure(REPO_ROOT, clone_dir)

    readme = clone_dir / "readme.rst"
    readme.write_text(readme.read_text() + "\n# test append\n")

    result = sp.run(
        ["nix", "develop", "-c", "git", "commit", "-am", "test"],
        cwd=clone_dir,
        capture_output=True,
        text=True,
        timeout=300,
    )
    _assert_commit_succeeded(result)


@pytest.mark.slow
def test_nix_develop_heals_stale_precommit_hook(tmp_path):
    """`nix develop` must repair a stale pre-commit hook in an existing repo.

    This reproduces the failure that actually bit us: a repo whose hooks were
    installed by an earlier setup, so ``.git/hooks/pre-commit`` points at the
    wrong pre-commit while the rendered config symlink is already up to date.
    git-hooks.nix keys its reinstall on the config symlink, so it leaves the
    stale hook untouched and every commit fails. The flake's self-heal must
    replace it.

    A single fresh clone does NOT exercise this -- it has no pre-existing hook.
    So we let `nix develop` install the hooks once, then corrupt the installed
    hook (leaving the config symlink matching) before committing.
    """
    clone_dir = tmp_path / "cloned_repo"
    _clone_and_configure(REPO_ROOT, clone_dir)

    # Pass 1: let the shellHook install the config symlink and hooks.
    sp.run(
        ["nix", "develop", "-c", "true"],
        cwd=clone_dir,
        check=True,
        capture_output=True,
        text=True,
        timeout=300,
    )

    # Corrupt the installed hook so it neither points at the right pre-commit
    # nor would succeed if it ran. The config symlink is left intact, so
    # git-hooks.nix's own shellHook will consider the repo up to date and skip
    # reinstalling -- only the flake's self-heal can fix this.
    installed_hook = clone_dir / ".git" / "hooks" / "pre-commit"
    assert installed_hook.exists(), "expected pass 1 to install a pre-commit hook"
    installed_hook.write_text("#!/usr/bin/env bash\necho STALE_HOOK_RAN >&2\nexit 1\n")
    installed_hook.chmod(0o755)

    readme = clone_dir / "readme.rst"
    readme.write_text(readme.read_text() + "\n# test append\n")

    # Pass 2: the commit must self-heal and succeed.
    result = sp.run(
        ["nix", "develop", "-c", "git", "commit", "-am", "test"],
        cwd=clone_dir,
        capture_output=True,
        text=True,
        timeout=300,
    )
    _assert_commit_succeeded(result)
    assert (
        "STALE_HOOK_RAN" not in result.stdout + result.stderr
    ), "the stale pre-commit hook was executed instead of being replaced"


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
