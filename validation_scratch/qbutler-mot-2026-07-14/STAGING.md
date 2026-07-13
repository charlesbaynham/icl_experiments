# QButler MOT-chain validation — STAGED submission ladder (Track B, on CLEAR)
Owner: qb-validate. Written 2026-07-14 (dark, rig blocked by human RID 77566 pri 0).
repo_rev = **82a5f0a7** (origin/feature/precompiled-cal-kernels tip; a3addb4d + one WP-B test; reachable on GitLab origin → master can fetch). log_level=20. arguments per body. **priority left OUT — coordinator sets negative (e.g. -30).**

## The DAG (verified, file:line)
Linear MOT chain, furthest-first fix walk: **SingleXODT → RedMOT → BlueMOT**
- RedMOTCalibration.add_dependency(BlueMOTCalibration)  red_mot.py:55
- SingleXODTCalibration.add_dependency(RedMOTCalibration)  xodt_calibration.py:53
- BlueMOTCalibration = leaf (root of chain)
Staleness timeouts: blue 300s, red 300s (both "testing only"), xodt 3600s.
Optimizable params: BlueMOTCalibration.push_setpoint (min0/max2, default 0.8), RedMOTCalibration.aom_frequency (min 364.436e6, max 364.836e6 Hz, default 364.636e6). XODT = CHECK-ONLY (no optimizable params).
Committed-optimum datasets (also the param defaults): `BlueMOTCalibration.push_setpoint`, `RedMOTCalibration.aom_frequency`.
Live DAG datasets: `calibrations.dag` {nodes,edges}, `calibrations.status` {class:{status,last_check,timeout,data}}, `calibrations.optimizer` {class:{param_names,points,data,status,started}}. Status Flag: OK=0, BAD_EXPIRED=1, BAD_DEPS=2, BAD_DATA=4, INVALID_DATA=8.

## Submit bodies (file / class_name)
| # | client | file | class_name |
|---|--------|------|-----------|
| canary | EnsureBlueMOT | repository/calibrations/ensure_blue_mot.py | EnsureBlueMOT |
| 2 | EnsureRedMOT | repository/calibrations/ensure_red_mot.py | EnsureRedMOT |
| 3 | EnsureXODT | repository/calibrations/ensure_xodt.py | EnsureXODT |
(Raw scan exps if needed: RedMOTCalibrationExp red_mot.py:142, SingleXODTCalibrationExp xodt_calibration.py:121. No BlueMOTCalibrationExp exists.)

## BOUNDED-SUBMIT FORM (resolved with qb-complete, code owner)
**Bare `arguments={}` self-terminates** — no scan axis needed. ndscan `TopLevelRunner.build` defaults `no_axes_mode=NoAxesMode.single` → `_continue_running=False` → `_run_continuous` runs `run_once` EXACTLY ONCE and completes. (The infinite loop only happens if you EXPLICITLY select continuous/repeat mode. Confirmed by the 07-12 dark-rig demos completing with `arguments={}`, not hanging.)
**Bounded body (all three clients):** `submit_experiment(file, class_name, arguments={}, repo_rev=82a5f0a7, log_level=20, priority=<coordinator, negative>)`. One `run_once`: recalibrate_if_needed escapes → host walks the fix (bounded by max_recalibrations=20) → precompiled fast re-entry (WP-A) → completes. Self-terminating, no-cancel-safe.
- This single-run path exercises escape/resume via **drive_with_recalibration (WP-A)**, NOT patch_ndscan (WP-B). WP-B only engages with a real scan axis — not needed for MOT-chain-on-atoms.
- **CANARY = the single-mode confirmation gate:** EnsureBlueMOT should self-complete within ~optimizer-sweep-time (blue ~11-pt push_setpoint sweep + one 30s idle ≈ a few min). If it self-completes (leaves schedule, `completed==true`) → single-mode confirmed, run the rest of the ladder confidently. If it's still "running"/idling ~15-20 min past the sweep → continuous mode engaged unexpectedly → flag Charles (can't cancel tonight; a MOT-only idle is benign, killable in the morning).
- Optional WP-B scanned-escape check: QbutlerScannedEscapeDemo scan_index 0..4 (dark-safe). Do NOT scan min_ok_fluorescence for bounding (mutates the OK threshold) — use an inert axis if a scan is ever wanted.

## Ordering + per-run judging (sanity windows from baselines)
Baselines: atoms healthy through XODT ~21:00Z (blue 77534; red 77535 sum 1.89e7; XODT 77536=86% healthy ref). 07-04: blue push opt 0.6V, red opt AOM 364.6453 MHz, biases (0.473,0.085,-1.020). Card: BlueMOT.push_setpoint 0.8V, RedMOT.aom_frequency 364.636 MHz.

**PRESENCE GATE (every stage): >10k atom_number OR localized blob; 1-3k scattered/negative = noise floor = NO atoms → stop the line.** Judge by dataset (`ndscan.rid_<RID>.completed==true`) + a visual frame check (localized blob), not tool status. Frames into the note.

1. **CANARY EnsureBlueMOT** (arguments={}, single). PASS iff: completed==true; `calibrations.status[BlueMOTCalibration].status==0` (OK); committed `BlueMOTCalibration.push_setpoint` in [0.4,1.0] V (baseline 0.6-0.8); `calibrations.optimizer[BlueMOTCalibration]` sweep shows a clear fluorescence peak (data > min_ok_fluorescence=2.0); points 1..N recall (no re-measure) → fast. If blue can't converge / fluorescence flat → loading collapsed → STOP, flag, don't proceed up chain.
2. **EnsureRedMOT** (arguments={}, single). PASS iff: blue still OK (recalled, not re-measured); `calibrations.status[RedMOTCalibration].status==0`; committed `RedMOTCalibration.aom_frequency` in [364.44,364.84] MHz, expect ~364.64 (baseline 364.6453); red optimizer sweep shows atom_sum peak > min_ok_atom_sum=2.0e6 (baseline sum 1.89e7).
3. **EnsureXODT** (arguments={}, single). PASS iff: chain (blue,red) OK recalled; `calibrations.status[SingleXODTCalibration].status==0`; XODT check data (fluorescence) > min_ok_fluorescence=1e6; **visual: localized XODT blob in the andor frame** (baseline 77536=86% healthy). XODT is check-only — if XODT reads BAD it CANNOT be optimized (surfaces failure); an upstream break is the intended demo.

>>> PRE-RUN STATE (read 2026-07-14, dark): committed-optima datasets NOT yet populated (calibrations.* all empty; no cal has run). So Track B's first EnsureX run starts each optimizable param from its CODE DEFAULT (push_setpoint=0.8, aom_frequency=364.636e6). Sabotage-restore of RedMOTCalibration.aom_frequency = set back to 364.636e6 (the default), since there is no prior committed value to preserve. Confirm the pre-sabotage value live before breaking, in case a cal has run by then.

## Escape / re-entry + sabotage proofs (after clean chain)
- **Recall proof:** immediately re-submit EnsureXODT (arguments={}) within timeouts → ZERO measurements, all nodes recall from calibrations.status → fast completion. Judge: no new optimizer points appended; status last_check unchanged for in-timeout nodes.
- **Sabotage → chain fix (in dependency order):** detune the committed red AOM ~150 kHz within the re-sweep window — set dataset `RedMOTCalibration.aom_frequency` to 364.636e6 - 150e3 = 364.486e6 (stays in [364.436e6,364.836e6]). Then run EnsureXODT (arguments={}): red's next check reads atom_sum < min_ok_atom_sum → BAD_DATA → escape → host re-optimizes red (blue recalled OK, not re-measured) → re-commits aom_frequency → XODT recovers OK. Judge: optimizer trace shows a fresh RedMOT sweep, blue untouched, final status all OK. **RESTORE** committed aom_frequency to its pre-sabotage value after (record the original first). Alt lever: raise min_ok threshold (high-but-reachable) — do NOT set unachievable (aborts after max_recalibrations=20).
- **Scanned escape/resume mechanics (dark-safe, can run even without atoms):** QbutlerScannedEscapeDemo (repository/calibrations/qbutler_scanned_escape_demo.py, class QbutlerScannedEscapeDemo) scan scan_index 0..4 (5pts). Proves mid-scan CalibrationEscape + resume (every point once, single escape line in log). Good first live-escape confidence check.

## RISKS / caveats
- **15s ARTIQ build watchdog** (client.py:368-374): a client whose fragment-tree build > 15s is KILLED at submission. Killed EnsureClockPiTimes on 07-12. Per qb-complete: only the HEAVY clock chain (EnsureClockPiTimes) hits this; the MOT/trap Ensure* (blue/red/XODT) have LIGHT trees, dark-validated 77451-77461, build well under 15s → clear tonight. Do NOT add EnsureClockPiTimes to the bare-submit set (gated on the LMT-lazy-builds card). Blue-canary-first still sound. WP-A confirmed on 82a5f0a7: single-mode escape re-entry = ~0.24s precompiled path (no recompile).
- max_recalibrations=20 (class attr, not an arg) bounds the fix loop — an unconvergeable node aborts after 20.
- LMT/clock-cal coil-driver contention: MOT-chain cals don't grab the clock coil driver, but do NOT interleave with DeclarativeLMT/clock cals on the Tenma driver (EADDRINUSE). Serialize.
- Every submit: arguments handled (never null), priority negative (coordinator), repo_rev=82a5f0a7, log_level=20.

## Leave-safe (per stage + end)
- Field/bias scans leave coils at last point — MOT cals optimize biases (red). RESET coils to nominal at end (run a blue check last, or reset explicitly).
- Restore any sabotaged dataset (RedMOTCalibration.aom_frequency) to pre-sabotage value.
- Optima are dataset-only; live aion checkout stays on master (run by ref). Never touch DISABLE_EM_GAIN (currently False by Charles). No clock cals, no Relock698Cavity.

## Judging pipeline (built + proven, Track A)
- scratch/2026-07-14-qbutler-mot-validation/qbval_plot.py — ndscan scan → plot+judge (PROVEN on live 77566).
- scratch/2026-07-14-qbutler-mot-validation/cal_dag_render.py — calibrations.dag/status/optimizer → DAG figure + optimizer sweeps + judge table (PROVEN on synthetic MOT-chain payload; unit-tested). Use --payload for saved json or live /values endpoint.
- .venv in that dir has matplotlib/numpy/scipy. REST reads: https://artiq.stronlab.net/api/datasets/values?names=<comma-list> (targeted) or /api/datasets (full 15MB dump).
