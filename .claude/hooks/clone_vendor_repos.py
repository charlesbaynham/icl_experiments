#!/usr/bin/env python3
"""Clone vendored ndscan and artiq at the exact commits locked in flake.lock / poetry.lock."""
import json
import os
import subprocess
import sys


def run(cmd: list[str]) -> None:
    print(f"  $ {' '.join(cmd)}", flush=True)
    subprocess.run(cmd, check=True)


def checkout_vendor(name: str, url: str, rev: str) -> None:
    d = f"vendor/{name}"
    if os.path.isdir(f"{d}/.git"):
        current = (
            subprocess.check_output(["git", "-C", d, "rev-parse", "HEAD"])
            .decode()
            .strip()
        )
        if current == rev:
            print(f"  {name}: already at {rev[:8]}", flush=True)
            return
        print(f"  {name}: updating {current[:8]} → {rev[:8]}", flush=True)
    else:
        print(f"  {name}: cloning {url} @ {rev[:8]}", flush=True)
        run(["git", "init", d])

    # Fetch the specific commit by SHA (works on GitLab with allowAnySHA1InWant)
    run(["git", "-C", d, "fetch", "--depth=1", url, rev])
    run(["git", "-C", d, "checkout", "FETCH_HEAD"])
    print(f"  {name}: ready", flush=True)


def find_artiq_in_flake_lock() -> tuple[str, str]:
    with open("flake.lock") as f:
        nodes = json.load(f)["nodes"]
    for node in nodes.values():
        locked = node.get("locked", {})
        url = locked.get("url", "")
        # Match the artiq fork, excluding unrelated packages that share the "artiq" name
        if (
            "artiq" in url
            and "comtools" not in url
            and "pyaion" not in url
            and "ndscan" not in url
            and "rev" in locked
        ):
            return url, locked["rev"]
    raise RuntimeError("artiq entry not found in flake.lock")


def find_ndscan_in_poetry_lock() -> tuple[str, str]:
    url = rev = None
    in_ndscan = in_src = False
    with open("poetry.lock") as f:
        for line in f:
            line = line.rstrip()
            if line.startswith("[[package]]"):
                in_ndscan = in_src = False
            elif line == 'name = "ndscan"':
                in_ndscan = True
            elif in_ndscan and line == "[package.source]":
                in_src = True
            elif in_src and line.startswith("url = "):
                url = line.split('"')[1]
            elif in_src and line.startswith("resolved_reference = "):
                rev = line.split('"')[1]
    if not url or not rev:
        raise RuntimeError("ndscan entry not found in poetry.lock")
    return url, rev


os.makedirs("vendor", exist_ok=True)

failed = []
for name, finder in [
    ("artiq", find_artiq_in_flake_lock),
    ("ndscan", find_ndscan_in_poetry_lock),
]:
    print(f"\nVendoring {name}...", flush=True)
    try:
        url, rev = finder()
        checkout_vendor(name, url, rev)
    except Exception as exc:
        print(f"  WARNING: {exc}", file=sys.stderr, flush=True)
        failed.append(name)

if failed:
    print(f"\nWARNING: could not vendor {', '.join(failed)}", file=sys.stderr)
    sys.exit(1)
