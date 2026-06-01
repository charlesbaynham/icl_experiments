---
name: ndscan-artiq
description: Use when understanding ndscan or artiq code, reading ndscan experiment fragments, understanding ARTIQ kernel constraints, exploring scan parameter types, or navigating the ndscan/artiq source code.
---

# Understanding ndscan and ARTIQ Code

Reference source for ndscan and ARTIQ is cloned at session start into `vendor/`, at the exact commits locked in `poetry.lock` (ndscan) and `flake.lock` (artiq).

## Source locations

- `vendor/ndscan/` — ndscan fork (aion-physics GitLab), commit from `poetry.lock`
- `vendor/artiq/` — ARTIQ fork (aion-physics GitLab), commit from `flake.lock`

## Key ndscan paths

| What | Where |
|---|---|
| ExpFragment base class | `vendor/ndscan/ndscan/experiment/fragment.py` |
| Entry points (`make_fragment_scan_exp`) | `vendor/ndscan/ndscan/experiment/entry_point.py` |
| Parameter types (FloatParam, BoolParam, …) | `vendor/ndscan/ndscan/experiment/parameters.py` |
| Result channels | `vendor/ndscan/ndscan/experiment/result_channels.py` |
| Scan specs | `vendor/ndscan/ndscan/experiment/scan_generator.py` |

## Key ARTIQ paths

| What | Where |
|---|---|
| EnvExperiment / HasEnvironment | `vendor/artiq/artiq/experiment.py` |
| @kernel / @rpc decorators | `vendor/artiq/artiq/language/core.py` |
| Core device | `vendor/artiq/artiq/coredevice/core.py` |
| RTIO primitives (delay, now_mu, …) | `vendor/artiq/artiq/language/units.py` |

## Usage

When asked to understand, debug, or extend ndscan or ARTIQ behaviour, read the relevant source files directly from `vendor/`. For example:

```bash
# Inspect the ExpFragment base class
cat vendor/ndscan/ndscan/experiment/fragment.py

# Find all parameter types
grep -n "class.*Param" vendor/ndscan/ndscan/experiment/parameters.py
```

If `vendor/` is missing (e.g. network unavailable at session start, or GitLab authentication not configured), fall back to the GitHub mirror of upstream ndscan: https://github.com/OxfordIonTrapGroup/ndscan
