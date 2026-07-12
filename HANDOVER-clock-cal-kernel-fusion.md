> **[RETIRED 2026-07-12]** This branch and approach are **superseded**. The fused-kernel
> heterogeneity wall (§7) was dissolved architecturally: qbutler now runs the calibration
> DAG on the host with per-submission background-precompiled per-node kernels and a
> `CalibrationEscape` re-entry protocol (rig-validated RIDs 77433-77461; all six Ensure*
> cals compile in CI including the three clock cals). See branch
> `feature/precompiled-cal-kernels` + `plans/2026-07-11-precompiled-cal-kernels-plan.md`
> (agent_workspace) + icl PR #84. This document is kept as the record of why fusion
> cannot work (§5-§7 remain the best explanation of the ARTIQ unification mechanics).

# Handover: kernel-driven clock calibrations & the fused-kernel heterogeneity wall

**Branch:** `test/ensure-kernel-run-once-compile-coverage` (icl_experiments), based on
`feature/calibrations` (`23356380`). Tip at handover: **`439e8876`**.
**Status:** blue / red / XODT `Ensure*` cals compile; the **3 clock cals do not**,
blocked on an architectural problem the current approach cannot solve on its own.
Do not merge yet. Read this whole file before touching anything.

---

## 1. What this branch is for

`test_compile_all.py` compiles every ndscan `Fragment` in the repo. Previously the
`Ensure*` calibration clients had a **host** `run_once`, so `test_compile_all`'s
precompiler (which only compiles `@kernel` lifecycle methods, fused into one kernel
like production's `_FragmentRunner`) never compiled the qbutler DAG-fix kernel — which
is exactly why the beam-setter unification bug reached the rig as `EnsureRedMOT`
RID 77386 instead of being caught in CI.

This branch:

1. Makes every `Ensure*Frag.run_once` `@kernel`, so CI actually compiles each
   calibration's fused DAG-fix kernel.
2. Fixes the resulting kernel-unification failures.

Goal: **all six `Ensure*` cals compile in `test_compile_all`** (EnsureBlueMOT,
EnsureRedMOT, EnsureXODT, EnsureClockDelivery, EnsureClockPiTimes, EnsureClockCentre).

---

## 2. Current compile state (verified, `nix run .#pytest -- tests/test_compile_all.py -k ... -n0`)

| Cal                                                              | Status                             |
| ---------------------------------------------------------------- | ---------------------------------- |
| EnsureBlueMOT                                                    | ✅ compiles (single-node control)  |
| EnsureRedMOT                                                     | ✅ compiles (was RID 77386; fixed) |
| EnsureXODT                                                       | ✅ compiles                        |
| the 4 previously-xfailed `ClockSpec*` fragments                  | ✅ compile                         |
| **EnsureClockDelivery / EnsureClockPiTimes / EnsureClockCentre** | ❌ **fail — see §7**               |

The 3 clock cals all share the same failure. Do not chase them independently; fixing
the shared root fixes all three.

---

## 3. Branches, MRs, flake pins (operational wiring — important)

- **pyaion !77 — MERGED** into pyaion master (`51b5017`). Made the beam-setter helper
  dataclasses per-subclass (`__init_subclass__`) and keyed `make_urukul_init` on the
  channel set. This is the fix for the original RID 77386 clash.
- **pyaion !78 — OPEN.** Branch `feature/cache-set-beams-to-default`
  (tip `4a5655d`). Caches `make_set_beams_to_default` by args (like `make_urukul_init`).
  Needed by this icl branch.
- **This icl branch temporarily pins pyaion at the !78 branch** in BOTH `flake.nix`
  (`inputs.pyaion.url = "...pyaion.git?ref=feature/cache-set-beams-to-default"`, with a
  `TODO: revert to master` comment) and `poetry.lock`/`pyproject.toml`
  (`branch = "feature/cache-set-beams-to-default"`). **After !78 merges, revert both to
  master** and run `nix flake update pyaion` + `nix develop -c poetry update --lock pyaion`.
- **Nix gotcha:** the _flake input_ (`flake.lock`) is the authoritative pyaion source,
  NOT `poetry.lock`. Changing `poetry.lock` alone does nothing — the env keeps the old
  pyaion. Use `nix flake update pyaion`. (Repo convention is to bump both locks in step.)
- `test_compile_all` needs the pyaion cache to be present. To confirm the built env has
  it: `nix develop -c python -c "import pyaion.fragments.default_beam_setter as m; print('_set_beams_subclasses' in open(m.__file__).read())"`.

Remotes: push feature branches to BOTH `origin` (gitlab) and `github`. PRs live on
GitHub. Never push master/main. Agent commits use `--no-gpg-sign`.

---

## 4. What's been done on this branch (commit-by-commit)

- `0988b87b` — `@kernel run_once` on all 5 original `Ensure*`; removed the
  `URUKUL_INIT` xfails in `test_compile_all.py`.
- `d96aad4d` — bump pyaion to `51b5017` (!77).
- `6e93aa5b` — review fixes: dropped the explicit `prepare_kernel_fix()` calls (the
  calibration's own `host_setup` auto-runs `prepare_kernel_ops`); restored
  `repository/lib/calibrations/_fit_helpers.py` (was missing on the base, broke clock
  cal _imports_); made `ensure_clock_centre.py` `run_once` `@kernel`.
- `ecac8803` — kernel-ified `CoarseClockCentreCalibration.check_own_state` (RPC the
  excitation read; the numpy `fit_peak_x` stays in the **host optimizer**
  `_coarse_fit_optimizer`, which is fine); lifted `RedBeamSettings` to module level;
  cached `make_toggle_list_of_beams`; lifted `ImagingDeviceSetup` +
  `ConstantBeamsInDeviceSetup`; per-enclosing-type subclass for `PulseDMARecording`.
- `3cf15d7d` — added the **`specialise_per_enclosing_type` helper**
  (`repository/lib/fragments/per_enclosing_type.py`) and used it for the recorder,
  the andor camera control, and the em-gain setter.
- `439e8876` — lifted the remaining 5 `build_fragment`-local Fragment classes to module
  level (3 with back-references → `specialise_per_enclosing_type`; 2 without → lift only).

**Blue/red/XODT stayed green throughout — verify this after any change.**

---

## 5. The core mechanic you must understand (ARTIQ type unification)

ARTIQ's compiler infers **one type per `(class, attribute)` and one signature per
method, across the entire compiled kernel**, keyed on the _concrete_ Python class
(subclass ≠ base; two `<locals>` classes with the same name are distinct types).

The qbutler kernel DAG-fix (`prepare_kernel_ops` in the vendored `qbutler/calibration.py`)
compiles the **whole dependency walk into ONE kernel** — `_fsk_driver` calls each dep
node's `check_own_state()` / `fix_own_state()`. So every calibration's measurement
fragment in the DAG is compiled together in one kernel.

Two failure families arise from this:

**(a) Per-instance / factory-made classes** — a class minted inside `build_fragment`
(or by a `make_*` factory called there) is a _fresh class per call_. Two instances of
the "same" logical thing get distinct types → cannot unify. **Fix = make it one shared
class**: lift `<locals>` classes to module scope; cache factory functions by their args
(`make_urukul_init` frozenset cache; `make_set_beams_to_default` cache in !78;
`make_toggle_list_of_beams` cache). All done.

**(b) A shared class that carries a member typed to its enclosing fragment** — e.g. a
back-reference (`outer_self`), a config object, or a bound method. One shared class
cannot hold that member as several enclosing types at once. **Fix = the helper**
(`specialise_per_enclosing_type`, §6) — a distinct subclass per enclosing type.

Families (a) and (b) are duals. (a) needs _sharing_; (b) needs _splitting_.

---

## 6. The helper — `specialise_per_enclosing_type`

`repository/lib/fragments/per_enclosing_type.py`:

```python
def specialise_per_enclosing_type(base_cls, enclosing_type) -> type:
    """Distinct cached subclass of base_cls per enclosing_type."""
    ...
    cls = type(f"{base_cls.__name__}_for_{enclosing_type.__name__}", (base_cls,), {})
```

Call it where you build the subfragment: `specialise_per_enclosing_type(TheClass, type(self))`.
Used at (all verified, blue/red/XODT still compile):

- `dma_actions_after_drop.py` — `PulseDMARecording` (outer_self back-ref).
- `andor_imaging/imaging_base.py` — `AndorCameraControl` (measurement-specific
  `camera_config`).
- `andor_imaging/em_gain.py` — `_CallFuncOnDeviceSetup` (a bound method) — **does NOT
  actually resolve the clash, see §7**.
- `clock_spectroscopy.py` `TurnOnClockDeliveryAOM`, `clock_shelving.py`
  `_ResetSlicingTime`, `clock_interferometry_with_signal.py` `SignalInjector` (all
  back-references, lifted + specialised).

The helper is correct and worth keeping for the genuine **data-holder** cases. It is
NOT sufficient for the remaining blocker.

---

## 7. THE WALL — what's actually blocking the 3 clock cals

Current failure (all 3 clock cals):

```
em_gain.py:38  self.func_to_call()
error: cannot unify <instance ..._CoarseClockLineFrag>
                with <instance ...NarrowDownAfterSliceFrag>
```

`_CallFuncOnDeviceSetup.func_to_call` is bound to `EMGainMixin._set_gain_if_changed`,
a **`@kernel` method defined once on the mixin**. The clock DAG-fix fuses several
**distinct measurement types that all inherit `EMGainMixin`** into one kernel:
`_SimpleSingleXODTBGCorrectedFrag` (XODT), `_CoarseClockLineFrag` (coarse),
`NarrowDownAfterSliceFrag` (refined). So `_set_gain_if_changed` is called with several
different `self` types in one kernel, and **ARTIQ infers one `self`-type per method** →
unresolvable.

`specialise_per_enclosing_type` on the _wrapper_ does not help: the thing that can't
unify is the **shared method**, not a data member. You cannot monomorphise a mixin
`@kernel` method by call-site `self` with per-instance-subclass tricks.

Why only the clock cals: `EnsureRedMOT` fuses blue+red and compiles because those MOT
measurements don't drag in the em-gain imaging mixin; `EnsureXODT` compiles alone. It's
specifically **fusing several distinct em-gain-imaged measurement types into one kernel**
that breaks — and `_set_gain_if_changed` is just the first such shared method; there are
likely more behind it.

Note: `_CoarseClockLineFrag` (coarse) is a **subclass** of `NarrowDownAfterSliceFrag`
(refined) differing only in the `lmt_sequence` / `lmt_initial_population` class
attributes (`coarse_clock_centre.py:44`), so they share _all_ methods.

---

## 8. Options (this is the decision the Fable agent + Charles must make)

**A — Don't fuse heterogeneous measurements (recommended).** Change the qbutler kernel
DAG-fix so each node's `check_own_state` compiles as its **own** kernel (one compile +
upload per node) instead of one fused kernel for the whole walk. This makes the entire
class of problem — both the data-holder clashes AND the shared-method clashes —
disappear, because each kernel then sees exactly one measurement type. Cost: loses the
"single compile/upload for the whole DAG" optimisation (slower fix; probably acceptable).
This is a **qbutler** change (vendored under `qbutler/` in this repo; upstream
`github.com/charlesbaynham/qbutler`). It likely makes much of §6's helper cascade
_unnecessary for the clock cals_, though the helper stays valid for any genuinely-fused
homogeneous case.

**B — Collapse the measurement classes.** Make coarse/refined/XODT share one measurement
_class_ (parameterise `lmt_sequence`/config as instance data instead of subclassing), so
there is nothing to unify. Removes _this_ cascade but is fragile (any future heterogeneous
clock DAG reintroduces it) and is a lot of measurement-code surgery. Does not generalise.

**C — Accept the 3 clock cals stay host-`run_once`** (revert their `@kernel`), keep the
helper for the data-holder cases, and track the fused-kernel-heterogeneity limit as a
separate qbutler issue. Lowest risk, least value; leaves the clock cals without kernel
compile coverage.

**Recommendation: A.** It is the principled root fix and it's contained to qbutler. B and
C are symptom management. Confirm with Charles before implementing — this is his
architecture and A touches the core qbutler DAG-fix machinery.

---

## 9. How to reproduce & debug

```bash
cd /home/charles/agent_workspace/icl_experiments/.wt/feature-calibrations
# one cal, no xdist (compile tests false-fail under -n; always -n0):
nix run .#pytest -- tests/test_compile_all.py -k "EnsureClockDelivery" -n0 -q
# all six:
nix run .#pytest -- tests/test_compile_all.py \
  -k "EnsureBlueMOT or EnsureRedMOT or EnsureXODT or EnsureClockDelivery or EnsureClockPiTimes or EnsureClockCentre" -n0 -q
```

**Reading the errors:** ARTIQ `UnificationError` dumps are 100–300 KB of nested
`TInstance`. Extract the human diagnostic:

```bash
nix run .#pytest -- tests/test_compile_all.py -k "EnsureClockDelivery" -n0 -q 2>&1 \
 | grep -aoE "[A-Za-z0-9_/]+\.py:[0-9:+-]+ error: (cannot unify|host object has an attribute '[a-z_]+')[^{]*" \
 | sed -E 's#/nix/[^ ]+##g' | head
```

- `host object has an attribute 'X' of type A ... different from ... type B` → family (b)
  data-holder clash on attribute `X` between shared-class instances → helper or lift.
- `cannot unify <instance A> with <instance B>` at a `self.method()` call → **shared
  method** (the §7 wall) → helper will NOT fix it.
- Per-instance markers: `grep -oE "TInstance\('[^']*(<locals>|\.[0-9]+)'"` finds
  uncached factory/local classes (family (a)).

`--tb=line` hides the diagnostic behind a coverage table; the flake's pytest app forces
coverage, so grep the full output as above rather than trusting the tail.

---

## 10. Landmines — do NOT do these

- **`DISABLE_EM_GAIN` is a hardware safety interlock** (protects a >£30k camera). It
  lives in `em_gain.py` (`EM_GAIN_DISABLE_DATASET`). Do not alter, bypass, or
  "simplify" that dataset or the interlock check while refactoring em-gain code.
- **Do not revert the pyaion pin to master until !78 is merged** — the branch won't
  compile without the `make_set_beams_to_default` cache.
- **Never write the literal token F-I-X-M-E** into committed files — CI's
  `check_for_fixme` fails the build. Use "TODO"/"follow-up".
- **`-n0` for compile tests.** Under `-n`/coverage, `test_compile_all` false-fails via
  linecache contamination; rerun a suspected failure in isolation before believing it.
- **Never run pre-commit/formatters while a `test_compile_all` kernel compile is
  running** (linecache contamination → spurious crashes).
- `isort` (pre-commit) reorders imports on commit; if a commit is aborted by it, `git
add -A` and re-commit (the file is already fixed).
- Do not touch the live stronlab / running ARTIQ stack. This is all offline compile
  work. The stack has migrated to `aion.lan` (10.137.3.254); the old `artiq.baynham.me`
  proxy is 503 — irrelevant to this task, which needs no rig.

---

## 11. Key file:line references

- Helper: `repository/lib/fragments/per_enclosing_type.py`.
- The wall: `repository/lib/experiment_templates/mixins/andor_imaging/em_gain.py`
  (`_CallFuncOnDeviceSetup`, `_set_gain_if_changed`, the interlock).
- Coarse cal (kernel-ified check_own_state, host optimizer):
  `repository/lib/calibrations/coarse_clock_centre.py`
  (`_CoarseClockLineFrag:44`, `check_own_state`, `_coarse_fit_optimizer`).
- Refined cal (the template we mirrored): `repository/lib/calibrations/clock_delivery.py`.
- qbutler kernel DAG-fix (where option A would land):
  `qbutler/calibration.py` (`prepare_kernel_ops`, `fix_state_kernel`, ~line 596/669).
- `test_compile_all` precompiler (fuses device_setup/run_once/device_cleanup):
  `tests/fixtures.py` `fragment_precompiler`.
- Ensure clients: `repository/calibrations/ensure_*.py`.

---

## 12. Suggested first moves for the new session

1. Re-run the six-cal compile above to confirm the state (blue/red/XODT green, 3 clock
   fail at `em_gain.py:38`).
2. Read `qbutler/calibration.py` `prepare_kernel_ops` / `_fsk_driver` to scope **option
   A** (one kernel per node instead of one fused kernel). Confirm with Charles before
   implementing — it's the core DAG-fix machinery and "has the potential to make a lot of
   mess if handled badly" (his words).
3. Keep the helper and the lifts (they're correct and green); do not rip them out unless
   option A makes specific ones dead.
4. When !78 merges, revert the pyaion flake/poetry pins to master (§3).
