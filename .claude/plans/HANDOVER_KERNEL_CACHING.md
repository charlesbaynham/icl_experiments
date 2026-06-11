# Handover: Kernel Compilation Caching

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
