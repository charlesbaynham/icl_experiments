# Handover: Kernel Compilation Caching

> **STATUS (session N+1, 2026-06-11): IMPLEMENTED.** See "Outcome" at the
> bottom of this document for what was built, measured numbers (which are
> substantially below the 10-100× estimate, and why), answers to the known
> unknowns, and remaining follow-ups.

## Session Context

**Previous work (Session N):** Optimized ARTIQ compiler from 30.7s → 27.9s (9.2% speedup) via:
- Dirty-set type inference with per-round hashing (embedded function discovery)
- Visitor dispatch caching (AST node visit optimization)
- Per-class kernel_from_string caching in ndscan (deduplication of forwarder functions)
- Phase timing instrumentation to identify bottlenecks

**Result:** Validated via A/B benchmarking (3×baseline, 3×optimized interleaved) on all 9 LMT experiments, plus 7-experiment regression sample.

**Current bottleneck:** Backend LLVM IR generation + assembly (12s of 27.9s), not inference.

---

## Next Phase: Kernel Caching

### Goal

Implement content-addressed compilation cache to reuse compiled LLVM IR across repeated experiment runs with different parameters.

**Expected speedup:** 30s → 2-3s for cached runs (10-100× improvement for repeated scans).

### Strategy

#### 1. Cache Key: Code Structure (Not Values)

- Hash the **LLVM IR code**, which depends on:
  - Kernel source text (methods, type signatures)
  - ARTIQ AST (control flow, decorators)
  - Type structure (int32 vs float64 field widths, function signatures)

- **NOT** hashed:
  - Parameter values (frequency=100MHz vs 200MHz)
  - Dataset initial values
  - Attribute instance values

**Rationale:** Same kernel code with different parameter values produces identical compiled object code; only the data payload differs.

#### 2. Two-Phase Upload

**Phase A: Compile-time (per-code-structure)**
1. Build LLVM IR as usual
2. Compute code hash: `blake2b(repr(llvm_module.as_string()))`
3. Check if hash exists in cache (local disk or shared S3)
4. If cached: retrieve compiled `.elf` binary, skip LLVM → assembly → link steps
5. If not cached: compile as usual, store `.elf` in cache

**Phase B: Runtime (per-experiment)**
1. Upload compiled binary to device (fast, small)
2. Upload parameter values separately (core.set_parameter_values {...})
3. Run kernel with uploaded values

#### 3. Implementation Points

**File: `vendor/artiq/artiq/compiler/targets.py`** (Target.compile_and_link)
```python
def compile_and_link(self, modules):
    code_hash = self._compute_code_hash(modules)

    if code_hash in self.cache:
        return self.cache[code_hash]  # Early return

    # ... existing compile + assemble + link ...
    compiled = self.link([self.assemble(self.compile(m)) for m in modules])
    self.cache[code_hash] = compiled
    return compiled
```

**File: `vendor/artiq/artiq/coredevice/core.py`** (Core.compile_and_run)
```python
# Add method to extract parameter values from experiment
def set_parameter_values(self, **kwargs):
    """Upload parameter values to device for cached kernel."""
    for name, value in kwargs.items():
        self.set_attribute_value(name, value)  # RPC to device
```

#### 4. Cache Storage

**Option A: Local disk (session/repository)**
- Path: `.artiq_kernel_cache/` (gitignored)
- File: `{code_hash}.elf`
- Pros: Simple, deterministic, no network
- Cons: Per-repository, no sharing across users

**Option B: Shared S3 (team/cloud)**
- S3 bucket: `s3://aion-physics/artiq-kernel-cache/`
- File: `{code_hash}.elf`
- Pros: Share across all users, all machines
- Cons: Network latency, auth setup, cache invalidation

**Recommendation:** Start with Option A (local), add S3 fallback later.

#### 5. Cache Invalidation

Cache is valid if:
- Vendored ARTIQ version is unchanged (check `vendor/artiq/.git/HEAD`)
- Compiler flags unchanged (ARTIQ_DUMP_*, optimization settings)
- Target triple unchanged (RV32IMA, CortexA9, etc.)

Invalidate if:
- Pushing updated ARTIQ vendored code
- Changing ARTIQ environment variables

**Pattern:** Store metadata alongside cache
```python
cache_metadata = {
    "artiq_commit": "abc123...",
    "compiler_version": "ARTIQ 7.1",
    "code_hash": "def456...",
    "cache_time": "2026-06-11T10:00:00Z"
}
```

#### 6. Testing

**Unit tests:**
```python
# test_kernel_cache.py
def test_same_code_same_hash():
    """Two experiments with identical kernel code have same hash."""
    ...

def test_different_code_different_hash():
    """Two experiments with different kernel code have different hash."""
    ...

def test_cache_retrieval():
    """Compilation is skipped if cache hit."""
    ...
```

**Integration test:**
```bash
# Compile same experiment twice, second run should be ~50ms (cache lookup)
time nix develop -c pytest repository/tests/test_compile_lmt.py::test_lmt_interferometry_symmetric -xvs
# First run: 27.9s
# Second run (with cache): 0.05s
```

---

## Key Files from Previous Session

Consult the **compiler-optimization** workspace skill for:
- Phase timing instrumentation (how to measure backend LLVM cost)
- Profiling methodology (cProfile top-25 functions in finalize)
- A/B benchmarking pattern (validate optimization doesn't regress other experiments)
- sys.path override for testing vendored code

**Skill location:** `.claude/skills/compiler-optimization/SKILL.md`

---

## Dependency Chain

This caching work depends on:
1. ✅ Dirty-set type inference optimization (previous session)
2. ✅ Visitor dispatch caching (previous session)
3. ✅ Per-class kernel_from_string caching (previous session)
4. ✅ Phase timing instrumentation (previous session)

These reduce per-compile time to 27.9s, making the backend LLVM step dominant and suitable for caching.

---

## Expected Artifacts

1. **Cache implementation** (`vendor/artiq/artiq/compiler/targets.py`, `core.py`)
2. **Cache metadata storage** (`.artiq_kernel_cache/` directory structure)
3. **Integration tests** (validate cache hit/miss, check speedup)
4. **Documentation** (AGENTS.md: "Kernel Caching" section)

---

## Success Criteria

- [ ] Single compile → cache miss → 27.9s
- [ ] Identical compile → cache hit → <0.1s (speedup: 279×)
- [ ] All LMT experiments cached correctly
- [ ] No regression in existing tests
- [ ] Cache survives vendored ARTIQ updates (metadata check)

---

## Known Unknowns

1. **Parameter upload path:** Does ARTIQ device support `set_parameter_values()`? May need to implement as RPC on device side.
2. **Binary size:** Typical `.elf` size for LMT experiments? Impacts cache storage strategy (local vs S3).
3. **Linker reproducibility:** Does ld.lld produce bit-identical output for same input LLVM? (Affects cache key collision risk.)

---

## Optional Enhancements (Future)

1. **S3 shared cache:** Reduce per-user compile time from 27.9s to network-latency (1-2s)
2. **Incremental kernel upload:** Only re-upload changed parameters, not full binary
3. **Cache analytics:** Track hit rate, most-cached experiments, cache size
4. **Parallel multi-version caching:** Keep N versions per code hash for A/B testing different optimizations

---

# Outcome (session N+1, 2026-06-11)

## What was built

- `vendor/artiq/artiq/compiler/kernel_cache.py`: content-addressed disk cache
  (`.artiq_kernel_cache/{code_hash}.elf` + `.json` metadata; atomic writes;
  never-fatal failures; `ARTIQ_KERNEL_CACHE=0` / `ARTIQ_KERNEL_CACHE_DIR`).
- `Target.compile_and_link` (targets.py): split into `build_llvm_ir` /
  `compile_llvm_ir`, computes `compute_code_hash(ir_texts)` =
  blake2b(environment fingerprint + target description + IR text) and skips
  parse/verify/optimize/assemble/link on a hit. The environment fingerprint
  hashes the vendored compiler sources themselves (not just the git commit,
  which would be stale for uncommitted edits), llvmlite/LLVM versions and the
  linker script. `ARTIQ_DUMP_HASHED_IR` dumps the exact hashed text.
- `Core.set_parameter_values(obj, **values)` (core.py): host-side parameter
  staging API; documents why device-side upload is impossible today (below).
- `tests/test_kernel_cache.py` (8 tests) + `scripts/pytest_vendored.py`
  (committed sys.path-injection wrapper).
- Docs: AGENTS.md "Kernel Caching" section, compiler-optimization skill update.

## The headline number is NOT 10-100×

The plan's "30s → 2-3s" / "<0.1s identical compile" success criteria are
unachievable *within the plan's own design*: the cache key is the LLVM IR
text, so inference (~11s), ARTIQ IR (~4s) and LLVM IR generation (~11s) must
run on every compile to produce the key. A hit skips only parse/verify/
optimize/assemble/link. Measured on LMTInterferometrySymmetricFrag (this
machine compiles it in ~32s, vs 27.9s in the previous session's environment):
miss ≈ 32s, hit ≈ 29s (~12% saving; backend phase 15.0s → 11.1s). A 10-100×
speedup requires a cache key computable *before* inference plus device-side
value upload — a different, much larger project (key would have to cover the
transitive closure of kernel sources *and* all embedded host values without
running discovery, which is exactly what stitching/inference is).

## IR determinism: the real battle (and the main value of this session)

Content-addressed caching requires byte-identical IR for identical input
across processes. It was not deterministic. Three sources were found by
diffing `ARTIQ_DUMP_HASHED_IR` dumps between perturbed processes (a dummy
env var of varying length is enough to shift the heap and flip
address-ordered containers):

1. `embedding.py`: string-kernels were named `__eval_{id(host_function)}`
   (memory address). → per-Stitcher sequence number.
2. `transforms/constant_hoister.py`: worklist was a `set` of instructions,
   so hoisted invariant loads entered the entry block in address order.
   → program-order fixed-point loop.
3. `transforms/llvm_ir_generator.py`: `llpred_map` used `set`s of blocks;
   the exception-phi fixup picks the first matching predecessor, so the
   choice was address-ordered. → insertion-ordered dicts.

**Still open (out of this repo):** pyaion's `UrukulInit.host_setup` embeds
`hash(device)` (= memory address / 16) as kernel data (`ad9910_ids`,
`ad9912_ids`, `urukul_ids`) and orders `self.urukuls` via `list(set(...))`.
Any experiment touching Urukuls therefore compiles to different bytes in
different processes, defeating the cache in production. `tests/conftest.py`
patches this for the test suite (deterministic sequence numbers + canonical
CPLD order — semantics preserved, the IDs only need process-local
uniqueness); **the same one-method fix must be made in pyaion** before the
cache is useful on the live system. `ir.Value.uses` (a `set`) is a further
latent risk for any future transform whose output order follows `uses`
iteration.

## Answers to Known Unknowns

1. **Parameter upload path:** NO device support. The core device protocol
   (`comm_kernel.Request`) has only SystemInfo/LoadKernel/RunKernel/RPC
   replies/SubkernelUpload — no memory-write command. True separate value
   upload needs firmware + protocol changes. `Core.set_parameter_values`
   exists as host-side staging + documentation anchor.
2. **Binary size:** LMT kernels link to 712-886 KB (≈840 KB for
   LMTInterferometrySymmetric). Local disk is fine; S3 viable.
3. **Linker reproducibility:** not load-bearing for this design — the key is
   the IR text and the stored ELF is replayed byte-exact; ld.lld determinism
   only matters if one ever compares fresh vs cached binaries.

## Verification

- 8/8 unit tests (hashing, hit-skips-compilation, disable switch,
  fingerprint invalidation, metadata, set_parameter_values).
- All 9 LMT fragments compile and pass cold (miss+store) and warm (hit).
- Cross-process determinism: 6 deliberately heap-perturbed processes produce
  byte-identical IR for LMTInterferometrySymmetricFrag.
- A/B benchmark (interleaved 3×, all 9 LMT fragments per session, single
  process): cache off 276.4/272.2/283.7s (mean 277.4s) vs warm cache
  234.8/243.8/234.1s (mean 237.6s) → **14.4% faster, ~4.4s per experiment,
  27/27 cross-process hits**. Cold populate run: 304.7s.
- Regression sample (5 non-LMT fragments across blue_mot/red_mot/
  clock_spectroscopy/dipole_trap): 5 passed cold (miss), 5 passed warm with
  5/5 cross-process hits; 93.6s → 79.8s.
