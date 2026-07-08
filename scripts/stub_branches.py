#!/usr/bin/env python3
"""Print the stub-source branch list from stubs_sources.yaml, one ref per line.

Shared by scripts/refresh_stubs.sh (which builds the stub catalog from these
refs) and scripts/watch_master.sh (which watches these refs for changes), so the
generator and the watcher always agree on exactly which branches feed the
catalog. Takes the config path as an optional argument (default
stubs_sources.yaml).
"""

import sys

import yaml

config = sys.argv[1] if len(sys.argv) > 1 else "stubs_sources.yaml"
data = yaml.safe_load(open(config)) or {}
branches = data.get("branches")
if (
    not isinstance(branches, list)
    or not branches
    or not all(isinstance(b, str) for b in branches)
):
    sys.exit(f"{config}: expected a non-empty top-level branches: list")
print("\n".join(branches))
