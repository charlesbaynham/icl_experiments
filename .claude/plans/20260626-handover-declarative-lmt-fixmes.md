# Handover: Resolve declarative-LMT FIXMEs

**Branch:** `claude/declarative-lmt-fixmes-8nnmoz` (push here only; do NOT make a new branch)
**PR:** #36 (draft) → base `declarative-lmt`. https://github.com/charlesbaynham/icl_experiments/pull/36
**HEAD at handover:** `b1c34fa`

## Why this exists / what was asked

The repo owner filled the declarative-LMT work with `FIXME` markers (none on
`master`) and asked to grep them and resolve them, working directly on the branch
above. `FIXME` fails CI (`flake.nix` `check_for_fixme`: `rg FIXME` excluding only
`nix/`, `flake.nix`, `readme.rst`, `AGENTS.md`, `archived_experiments/`).

The 12 code FIXMEs were in 6 files: `lmt_sequence.py` (144, 250, 254, 256, 261),
`lmt_resonance.py` (22, 128), `pulse_intent.py` (1), `constants.py` (1562),
`lmt_declarative.py` (111, 122), `demo_declarative_lmt.py` (92).

## Decisions taken WITH THE OWNER (do not relitigate)

1. **`pulse_intent.py` ↔ `lmt_resonance.py` "duplication":** consolidate the
   shared vocabulary into `lmt_resonance.py` and delete `pulse_intent.py`.
2. **Internal state `"g"/"e"` → enum:** new `InternalState(Enum)`; module-level
   `GROUND`/`EXCITED` now bound to its members (importers unchanged).
3. **`MOMENTUM_KICK_DETUNING`:** derive from fundamental constants
   `h / (m_Sr87 · λ²)` (done in `constants.py`).
4. **`lmt_resonance.py:128`:** hardware-validation note → `TODO` (done).
5. **`lmt_sequence.py:144` (`Wait.param`):** just DELETE the FIXME comment, keep
   `param: str` (the sequence is a class-level list, so a `FloatParamHandle`
   can't exist at declaration time). Done.
6. **Callback redesign — the big one.** A `Callback` declares a list of
   `CallbackAction(state, m, delta_m, state_effect)`. At fire time each action is
   recorded as ONE ordinary `Kind.PULSE` intent row sharing a single `t_start`
   (the "flatten" model), so the 7-row record format is unchanged and the
   trajectory/spacetime predictors drop their callback-specific code. `state_effect`
   is the `StateEffect` enum (FLIP/SUPERPOSE/NONE) — done; resolves FIXMEs 250/254/256/261.
   - **IMPORTANT design correction (owner-confirmed):** there is NO "selective vs
     broadcast" / off-resonant concept. The trackers never modelled off-resonant
     excitation; every declarative pulse already addresses only its own `(state,m)`
     pair. A `CallbackAction` is treated EXACTLY like an ordinary pulse. What a
     callback adds over one pulse is only: (a) several simultaneous actions,
     (b) a pure-momentum-kick `StateEffect.NONE` (no g↔e flip), (c) zero actions
     (external trigger, no record/branch change). The old callback's
     "apply delta_m to every branch" broadcast was deliberately dropped.
   - **Dummy callback** added to `demo_declarative_lmt.py` (`DemoDeclarativeLMTCallback`):
     fires a normal pulse via the RAW, UNTRACKED `clock_up_dds.sw.on()/off()` path,
     because the action's intent is already registered by `register_intent_action`
     — using the tracked wrappers would double-count.
7. **AUTO/M_AUTO sentinels KEPT** (legacy `register_pulse` in clock_interferometry,
   clock_shelving, clock_spectroscopy, clock_spec_pulse_ratio, LMT_launch_mixins,
   dma_actions_after_drop depends on them).
8. **`flip`/`superpose` strings → `StateEffect` enum:** done (part of #6).
9. **LEAVE the 3 disabled-experiment FIXMEs** (`demo_declarative_lmt.py:99`,
   `lmt_declarative.py:112/123`). These mark intentionally-commented-out sequences
   (velocity-slice scanning). They STAY until the owner restores those sequences
   before merge — so the `Check for FIXME` CI gate is EXPECTED to stay red.

## What is DONE (committed + pushed)

- `e3645c1` Phase 1: consolidate vocabulary into `lmt_resonance` (Kind, StateEffect,
  AddressedState, M_AUTO, IntentEvent, intent_events_from_arrays moved; `InternalState`
  added; unified `_ground_class_of_pair` shared by `pair_ground_class` and
  `IntentEvent.addresses_pair`; `pulse_intent.py` deleted; `MOMENTUM_KICK_DETUNING`
  derived; `Wait` FIXME removed; all non-test imports repointed; `lmt_initial_population`
  updated to enum members in lmt_declarative/demo/red_mot_dynamic_roi/lmt_global_params).
- `dd58c4c` Phase 2: Callback flatten model. `CallbackAction`/`Callback` redesigned;
  `_apply_addressed_action` shared by `_compile_pulse` and `_apply_callback`;
  `register_intent_action` replaces `register_intent_callback`; `declarative_lmt.py`
  flat kernel arrays `_lmt_cb_action_*` + per-event (start,count) + fire loop;
  `trajectory.py`/`lmt_spacetime.py` deleted `_apply_callback`+`Kind.CALLBACK` branch
  and added the NONE pure-kick path to `_apply_pulse`; dummy callback added.
- `07b9749` Phase 3: tests migrated. `test_pulse_intent.py`→`test_intent_vocabulary.py`;
  imports repointed; population literals/`state=` → enum members; every `Callback(...)`
  → `actions=[CallbackAction(...)]`; new `test_callback_flatten.py`; refreshed stale
  example comment in `lmt_declarative.py`.
- `b1c34fa` docstring correction (the no-selectivity wording, decision #6 bullet).

## What REMAINS (the reason for the handover)

**CI is red and NOT yet verified to be green-able.** Two things must be done in the
Nix environment (which the prior session could not reach — see Environment below):

1. **Diagnose & fix the pytest collection failure.** On `07b9749` ALL 16 pytest
   shards fail identically. The job log shows the Nix env build, then `git-hooks.nix`
   pre-commit install, then `No data to report.` (coverage) and exit 1 — with NO
   pytest collection output or traceback. That pattern = pytest aborted at
   startup/collection before running any test (e.g. a conftest/import error), but the
   traceback wasn't captured in the CI log. **You must run pytest locally to see the
   real error.** Note `tests/conftest.py` does `from fixtures import *` — check that
   and the new/edited test modules import cleanly. The migrated tests use an alias
   `import lmt_resonance as pulse_intent` (ugly but valid). Likely culprits to check
   first: `tests/test_intent_vocabulary.py`, `tests/test_callback_flatten.py`,
   `tests/test_intenum_kernel_compile.py` (has a local `_IntentKind` mirror),
   `repository/tests/test_trajectory_applet.py`.
   - Run targeted host-side first (fast): `nix run .#pytest -- tests/test_lmt_sequence.py
     tests/test_callback_flatten.py tests/test_intent_vocabulary.py tests/test_lmt_resonance.py
     tests/test_ballistic_predictor.py tests/test_lmt_spacetime.py
     tests/test_roi_prediction_equivalence.py tests/test_lmt_global_params.py
     repository/tests/test_trajectory_applet.py -q`
   - Then the kernel-compile ones: `tests/test_intenum_kernel_compile.py`, and compile
     the two declarative fragments via `test_compile_all` selectors
     (`DeclarativeLMTSymmetricMachZehnder`, `DemoDeclarativeLMT`, `DemoDeclarativeLMTCallback`).
   - See the `running-tests` skill for exact invocation/pitfalls (`--no-cov` breaks
     pytest; full suite >1h — use selectors).

2. **Formatting / lint (`pre-commit`).** The agent edits were NOT black-formatted
   (black/isort/flake8 were unavailable without Nix). Run `pre-commit run --all`
   (or `nix develop -c pre-commit run --all`), let it reformat, and commit the result.
   This + (1) should make `Static analysis (pre-commit)` pass EXCEPT the FIXME gate.

3. **Commit + push** fixes to `claude/declarative-lmt-fixmes-8nnmoz` (use
   `git push -u origin <branch>`). PR #36 already exists — do not create another.

**Expected final CI state:** everything green EXCEPT `Check for FIXME`, which stays
red by owner decision #9 (the 3 disabled-experiment FIXMEs) until those sequences are
restored before merge. Make this explicit when reporting; do not "fix" those FIXMEs.

## Correctness notes worth re-verifying (already traced by hand, but confirm via tests)

- Compiler population walk (`lmt_sequence._apply_addressed_action`) must equal the
  trajectory/spacetime walk for a flattened callback. They share `_ground_class_of_pair`.
  Traced FLIP, SUPERPOSE, and the NEW `StateEffect.NONE` pure-kick — all agree. The NONE
  case is the only genuinely new pulse-path behaviour (previously NONE on a pulse was a
  no-op; now it's a pure momentum kick on the single declared population — safe because no
  `Kind.PULSE`+`NONE` rows existed before).
- Callback sign convention: `delta_m` plays the beam sign in the shared pairing rule.
  The old `Callback(delta_m=+2, state_effect="flip")` becomes
  `CallbackAction(state=EXCITED, m=0, delta_m=-2)` to express the same `(e,0)→(g,2)`
  transfer (`m_g = m - delta_m = 0-(-2) = 2`). The test encodes this explicit-pair convention.

## Environment notes

- Prior session: outbound git goes through a policy proxy that 403s
  `github.com/m-labs/sipyco` (a transitive flake input via the artiq fork). The
  session-start hook vendors `artiq` + `ndscan` but NOT `sipyco`, so `nix run`
  could not EVALUATE the flake locally (Cachix substitution worked for store paths,
  but flake-input git fetch is blocked). This is why we're moving to a Nix-ready env.
- `constants.py` and the physics modules (`lmt_resonance`, `lmt_sequence`,
  `trajectory`, `ballistic`) are artiq-free — host-side tests can in principle run
  with just scipy/numpy if Nix is still unavailable, but the canonical path is `nix run .#pytest`.
- The `nix-setup` and `running-tests` skills cover Nix install + test invocation.

## PR subscription

The session was subscribed to PR #36 activity. Expected-red checks to SKIP (not chase):
`Check for FIXME` (decision #9) and the pytest/pre-commit reds that items (1)/(2) above
resolve. Only investigate genuinely NEW/unexpected failures.
