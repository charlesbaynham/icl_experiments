#!/usr/bin/env python3
"""Run pytest against the vendored artiq/ndscan trees in vendor/.

The nix dev shell resolves artiq and ndscan from /nix/store, which does not
include uncommitted changes to the vendored copies. This wrapper injects the
vendored paths ahead of site-packages (which must happen before anything
imports artiq) and then hands over to pytest.

Usage:
    nix develop -c python scripts/pytest_vendored.py tests/test_kernel_cache.py -v
"""
import os
import sys

repo_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(repo_root, "vendor", "ndscan"))
sys.path.insert(0, os.path.join(repo_root, "vendor", "artiq"))

import artiq  # noqa: E402
import ndscan  # noqa: E402

assert "vendor" in artiq.__file__, f"artiq loaded from wrong path: {artiq.__file__}"
assert "vendor" in ndscan.__file__, f"ndscan loaded from wrong path: {ndscan.__file__}"

import pytest  # noqa: E402

if __name__ == "__main__":
    os.chdir(repo_root)
    sys.exit(pytest.main(sys.argv[1:]))
