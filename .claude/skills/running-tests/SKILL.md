---
name: running-tests
description: Use when running this repository's tests locally - unit tests, or compiling experiment Fragments for the core device via test_compile_all. Covers the nix run .#pytest invocation, targeted selectors, and pitfalls (full suite takes >1h; --no-cov breaks pytest).
---

# Running tests locally

All tests run through Nix - never make a python venv. If `nix` is not
available in this environment, apply the `nix-setup` skill first.

```bash
export PATH=/nix/var/nix/profiles/default/bin:$PATH   # if not already set

# Fast host-side unit tests (seconds)
nix run .#pytest -- tests/test_lmt_sequence.py -q

# Compile a single experiment Fragment for the core device (~1 min each,
# provided the aion-physics binary cache is configured)
nix run .#pytest -- tests/test_compile_all.py::test_build_all_fragments -k "lmt_declarative"
```

## Rules

- **Do NOT run the whole test suite or all of `test_compile_all.py`
  locally.** It compiles every Fragment in the repository and takes well
  over an hour. Always select the tests relevant to your change with file
  paths and/or `-k` selectors - a targeted Fragment compile takes about a
  minute and catches the same errors.
- Do not pass `--no-cov`: the pinned pytest does not accept it and aborts
  before collecting any tests, printing only a cryptic
  "No data to report.".
- The first `nix run .#pytest` of a session downloads/realises the
  environment (a few minutes with the Cachix cache); subsequent runs start
  immediately.

## Choosing what to run

- Changed host-side library code: run its unit-test file(s) in `tests/`.
- Changed a Fragment, mixin, or anything touching kernels: also compile the
  affected experiments with
  `tests/test_compile_all.py::test_build_all_fragments -k "<module or class name>"`.
  `-k` matches against `module.path / FragClassName` test IDs; classes whose
  names end in `Base` or `Mixin` are skipped as abstract.
- Long runs: launch in the background and poll the output file rather than
  blocking.
