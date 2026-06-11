---
name: compiler-optimization
description: Use when profiling ARTIQ compilation, running A/B benchmarks, overriding vendored code, or optimizing compiler performance.
---

# ARTIQ Compiler Optimization and Profiling

This skill documents the methodology for profiling ARTIQ compilation, testing optimizations via A/B benchmarking, and overriding system ARTIQ with vendored code.

## Quick Reference

### Phase Timing (identify bottlenecks)

```bash
export ARTIQ_PHASE_TIMING=1
nix develop -c pytest repository/tests/test_compile_lmt.py::test_lmt_interferometry_symmetric -xvs 2>&1 | grep "\[phase\]"
```

Expected output:
```
[infer] LMTInterferometrySymmetric converged: 32 visit rounds, 17 hash rounds, 3456 function visits (n_funcs=860)
[phase] llvm_ir_gen=6.52s parse_verify=0.13s optimize=0.89s
[phase] compile+assemble=7.64s link=0.21s
```

**Legend:**
- `[infer]` lines: type inference fixed-point loop stats (lines from `vendor/artiq/artiq/compiler/embedding.py`)
- `[phase]` lines: wall-clock timing for backend phases (lines from `vendor/artiq/artiq/coredevice/core.py` and `vendor/artiq/artiq/compiler/targets.py`)
- Inference loop converges in `visit_rounds` (discovery cascades) + `hash_rounds` (full type propagation)
- Total compile time ≈ `inference + [phase] times`

### Profiling (detailed flamegraph)

```bash
export ARTIQ_PROFILE_FINALIZE=1
nix develop -c pytest repository/tests/test_compile_lmt.py::test_lmt_interferometry_symmetric -xvs 2>&1 | grep -A 30 "cProfile"
```

Returns top 25 functions by cumulative time in the finalize (type inference) phase.

## Overriding System ARTIQ with Vendored Code

The nix dev shell pins ARTIQ to `/nix/store/`. To test vendored code (in `vendor/artiq/`), inject it into Python's module search path **before any imports**:

### Pattern: sys.path injection in Python script

```python
#!/usr/bin/env python3
import sys
import os

# Insert vendored paths FIRST, before any artiq/ndscan imports
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "vendor", "artiq"))
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "vendor", "ndscan"))

# NOW import artiq; it will load from vendor/
import artiq
import ndscan

# Verify correct modules are loaded
assert "vendor" in artiq.__file__, f"artiq loaded from wrong path: {artiq.__file__}"
assert "vendor" in ndscan.__file__, f"ndscan loaded from wrong path: {ndscan.__file__}"

# ... rest of script ...
```

### Why this is necessary

- `nix develop` loads system Python from `/nix/store/`, which has pre-installed artiq/ndscan
- Environment variables like `PYTHONPATH` do NOT override `/nix/store` site-packages
- `sys.path.insert(0, ...)` **must** happen before any `import artiq` statements
- Assertion checks prevent silent fallback to system packages

### Testing vendored code with pytest

A committed wrapper exists for the common case:

```bash
nix develop -c python scripts/pytest_vendored.py tests/test_kernel_cache.py -v
```

For custom setups, create a wrapper script that injects sys.path, then runs pytest:

```bash
#!/usr/bin/env bash
export BENCH_ARTIQ_PATH=/path/to/vendor/artiq
export BENCH_NDSCAN_PATH=/path/to/vendor/ndscan
nix develop -c python3 /tmp/bench_wrapper.py
```

Where `bench_wrapper.py` is:

```python
import sys
import os
os.chdir("/home/user/icl_experiments")
sys.path.insert(0, os.environ["BENCH_ARTIQ_PATH"])
sys.path.insert(0, os.environ["BENCH_NDSCAN_PATH"])

import artiq, ndscan
assert "vendor" in artiq.__file__
assert "vendor" in ndscan.__file__

import pytest
sys.exit(pytest.main([
    "repository/tests/test_compile_lmt.py",
    "-xvs",
    "--tb=short"
]))
```

## A/B Benchmarking (Interleaved)

To validate an optimization doesn't regress other experiments, run alternating baseline vs optimized builds to cancel machine-load drift.

### Pattern: Interleaved A/B test

```bash
for i in 1 2 3; do
    echo "=== BASELINE RUN $i ==="
    BENCH_ARTIQ_PATH=/tmp/vendor_baseline/vendor/artiq \
        BENCH_NDSCAN_PATH=/tmp/vendor_baseline/vendor/ndscan \
        nix develop -c python3 /tmp/bench_ab.py 2>&1 | grep -E "BENCH|\[infer\]|PASSED|FAILED"

    echo "=== OPTIMIZED RUN $i ==="
    BENCH_ARTIQ_PATH=/home/user/icl_experiments/vendor/artiq \
        BENCH_NDSCAN_PATH=/home/user/icl_experiments/vendor/ndscan \
        nix develop -c python3 /tmp/bench_ab.py 2>&1 | grep -E "BENCH|\[infer\]|PASSED|FAILED"
done
```

### Interpreting results

```
BENCH: test_lmt_interferometry_symmetric 30.7s
[infer] LMTInterferometrySymmetric converged: 32 visit rounds, 17 hash rounds, 3456 function visits
PASSED
```

- Wall-clock time (first number): varies by ~±2s due to machine load (why interleaving helps)
- Function visit count and convergence rounds: deterministic metric of optimization impact
- PASSED/FAILED: regression indicator

### Setting up baseline for comparison

```bash
# Clone pristine vendor repos to /tmp/vendor_baseline for first run
cd /tmp
git clone https://github.com/m-labs/artiq.git vendor_baseline/vendor/artiq
cd vendor_baseline/vendor/artiq
git checkout <original-commit-hash>  # Reset to pre-optimization state
```

Then use `BENCH_ARTIQ_PATH=/tmp/vendor_baseline/vendor/artiq` in baseline runs.

## Dirty-Set Type Inference (Key Optimization)

**File:** `vendor/artiq/artiq/compiler/embedding.py`

The type inference fixed-point loop re-visits embedded functions until convergence. Without optimization, each function's hash includes only its source code, missing that new host values have been injected for its types.

### How dirty-set tracking works

1. **Per-round hashing** (`TypedtreeHasher`): hash includes `(source, attribute_count, value_map_size)` to detect when types change
2. **Discovery cascades** (`_injected_nodes`): when a new embedded function is found, add to list instead of re-looping all functions
3. **Convergence check**: if no new functions and no new types, stop

**Impact:** Reduces iterations from ~17 to ~32 + 17 (discovery + propagation phases), but each phase is much faster.

## Visitor Dispatch Cache (Quick Win)

**File:** `vendor/artiq/artiq/compiler/_visitor_dispatch_cache.py`

Caches the resolution of `visit_<NodeType>` methods per (visitor_class, node_class) pair, avoiding `getattr()` per node visit. Compiler visits 4.7M+ nodes per LMT compile.

**Impact:** ~2-3% speedup, one-line install in `vendor/artiq/artiq/compiler/__init__.py`

## Kernel Caching (Implemented)

`artiq.compiler.kernel_cache` + `Target.compile_and_link` implement a
content-addressed cache for linked kernel binaries.

**Key:** blake2b of the LLVM IR text + environment fingerprint (compiler
sources digest, llvmlite/LLVM versions, target triple/features/linker
options). Host attribute values are embedded in the IR as global
initializers, so the key covers values as well as code; stale hits are
impossible, but a changed parameter value is a miss.

**What a hit skips:** parse/verify/optimize/assemble/link (~4s for LMT).
Inference + ARTIQ IR + LLVM IR generation (~26s) still run, because the IR
text is the key. Measured (interleaved A/B, 3 runs each, all 9 LMT
fragments, single process, this container): cache off 277.4s mean vs warm
cache 237.6s mean = 14.4% faster, ~4.4s per experiment; 27/27 cross-process
hits. Non-LMT sample (5 fragments): 93.6s → 79.8s. The original "30s →
2-3s" estimate would require a pre-inference cache key plus device-side
parameter upload, which the core device protocol does not support (no
memory-write command; see `Core.set_parameter_values`).

**Env vars:**

```bash
ARTIQ_KERNEL_CACHE=0            # disable
ARTIQ_KERNEL_CACHE_DIR=path     # default ./.artiq_kernel_cache
ARTIQ_DUMP_HASHED_IR=/tmp/x     # dump exact hashed text -> /tmp/x_hashed.ll
```

**Phase timing lines:** `[phase] kernel_cache=hit|miss code_hash=...`.

### IR determinism (prerequisite for cross-process hits)

Cross-process cache hits require byte-identical IR text from identical
input. Two address-dependent nondeterminism sources were fixed:

1. `embedding.py` `_quote_embedded_function`: string-kernels were named
   `__eval_{id(host_function)}` (a memory address). Now a per-Stitcher
   sequence number.
2. `constant_hoister.py`: the worklist was a `set` of instructions, so
   hoisted loads entered the entry block in address order. Now a
   program-order fixed-point loop.
3. `transforms/llvm_ir_generator.py`: `llpred_map` used sets of blocks; the
   exception-phi fixup emits the first matching predecessor, so the choice
   was address-ordered. Now insertion-ordered dicts.
4. **pyaion (test-suite patch only; needs the real fix upstream)**:
   `UrukulInit.host_setup` embeds `hash(device)` (memory addresses) as
   kernel data and orders CPLDs via `list(set(...))`. Patched
   deterministically in `tests/conftest.py`; production caching of
   Urukul-touching experiments stays broken until pyaion itself is fixed.

To debug a new nondeterminism source: run the same compile twice with
`ARTIQ_DUMP_HASHED_IR`, diff the dumps, and look for `id()`-derived names or
set/dict-of-objects iteration in whichever transform emitted the differing
lines. Note that `ir.Value.uses` is an unordered `set`, so any transform
whose *output order* follows `uses` iteration is a latent risk.

## Verification Checklist

After making optimizations, verify correctness:

```bash
# 1. Phase timing: check inference converged quickly
export ARTIQ_PHASE_TIMING=1
export ARTIQ_INFER_PASS_DEBUG=1
nix develop -c pytest repository/tests/test_compile_lmt.py -xvs 2>&1 | grep "\[phase\]\|\[infer\]"

# 2. Function count: deterministic indicator of optimization
# Should decrease (fewer duplicate embedded functions) or stay stable (same inference)

# 3. Full regression: run all 16 LMT experiments
nix develop -c pytest repository/tests/test_compile_lmt.py -v --tb=short

# 4. Broad regression: sample non-LMT experiments
nix develop -c pytest repository/tests/test_compile_all.py::test_cavity_lock -xvs
nix develop -c pytest repository/tests/test_compile_all.py::test_lmt_cooling -xvs
```

## Common Pitfalls

1. **Forgetting sys.path injection**: Script silently loads system ARTIQ instead of vendored
   - **Fix:** Add assertion checks to verify `__file__` contains `"vendor"`

2. **Running A/B with same baseline twice**: Invalidates comparison
   - **Fix:** Always clone baseline to separate directory before first run

3. **Benchmarking wall-clock without interleaving**: Machine load swings ±5-10s
   - **Fix:** Alternate baseline/optimized in same test loop

4. **Convergence looking worse (32 vs 17 rounds)**: Discovery cascades trade round count for per-round speed
   - **FIX:** Check hash rounds and function visit count, not just visit_rounds
   - **Expected:** visit_rounds ↑ (more discovery), hash_rounds ↓ or stable, total time ↓
