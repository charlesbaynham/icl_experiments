# Dynamic ROI from the red MOT — overnight results & handover

Date: 2026-06-13 (overnight, run by charlesbot)
Branch: `claude/dynamic-roi-red-mot` (off `claude/lmt-sequence-api-6dcd7f` + merged
`claude/pulse-recorder-opll-tracking-n8fjzx`). Live checkout left on this branch.

## TL;DR

- **Dynamic-ROI imaging of a DROPPED red-MOT cloud WORKS and is validated on hardware.**
  RID **74478**: a 3-point drop-time scan shows the grabber ROI repositioning to follow
  the predicted free-fall trajectory, with the cloud captured at a _constant_ position
  relative to the moving ROI — the definition of correct tracking. No RTIO underflow,
  EM gain 1 (not saturated).
- **The dynamic-ROI code itself is sound.** All the review findings (F1–F11) are
  implemented; the predictor is intent-driven (no Bordé branch explosion in the
  experiment path); 90 host unit tests + kernel compile all pass.
- **Two things block a fully turnkey result, neither is a correctness bug in the ROI code:**
    1. **Prediction-RPC latency/variance** on the shared master makes the tight in-shot
       prediction budget marginal (intermittent underflow). Fix below.
    2. **The declarative LMT launch sequence underflows when run from the red MOT**
       (~5.3 ms, _independent of the ROI prediction budget_ — confirmed identical at 9 ms
       and 20 ms). This is the clock-pulse-sequence timing (OPLL ramps / AOM switching),
       not the ROI work, and needs hands-on tuning.

## What was built (all committed + pushed)

- Pulse **intent** stream recorded alongside the pulse facts in `PulseDMARecording`
  (`register_pulse` default π-intent; `register_pulse_with_intent` / `register_clearout`
  / `register_intent_callback`; archived as `pulse_intent_record(_flat/_offsets)`).
- Intent-driven trajectory predictor `repository/lib/physics/trajectory.py`
  (kinematic population walker; ground/excited ports; multiplicity flags; gravity
  parabola; CameraGeometry projection). `ballistic.py` CameraGeometry now
  Gram-Schmidt-orthonormalises (F7).
- `DynamicROIImagingMixin` + `LMTCompensatedCameraConfig` rewrite: FK readout-frame ROIs
  (F6), ordered clamping + clip flag (F10), DMA-timebase rebasing (F4), mid-shot grabber
  reprogram (F5), pinned image time + slack budget/logging (F8). Diagnostics result
  channels. Trap/ROI params rebound to the experiment level so they are settable from
  the submit API.
- `RedMOTWithDMAExperimentBase` (red-MOT DMA record/playback) + `DeclarativeLMTRedMOTBase`
  (the declarative engine split base-agnostic + dipole/red-MOT variants; the engine now
  records explicit pulse intent).
- Three experiments in `repository/LMT/red_mot_dynamic_roi.py`:
  `RedMOTDropDynamicROI`, `RedMOTSlicedSpecDynamicROI`, `RedMOTLaunchDynamicROI_N{2,4,8}`.
  **EM gain is a parameter defaulting OFF** (safety) — enable per run.

## Lab run log (RIDs)

| RID      | Experiment   | Args                                 | Result                                                                                                              |
| -------- | ------------ | ------------------------------------ | ------------------------------------------------------------------------------------------------------------------- |
| 74466    | Drop         | defaults, em-gain off                | ✓ plumbing: prediction RPC ran, empty-port logic correct, slack +159 µs, signal present                             |
| 74468    | Drop         | em30, gauss fit                      | ✓ but EM gain 30 **saturates** the full cloud (sum 223M)                                                            |
| 74470/71 | Drop         | warm-up/slicing dev                  | underflow → drove the slicing fix                                                                                   |
| 74472    | Drop scan ×3 | em1, 8 ms budget                     | ✓ **first clean tracking proof**: predicted_gnd_y [251,242,229] falls, fitted tracks, slope correct ~10%            |
| 74478    | Drop scan ×3 | em1, 9 ms, trap (205,289), ROI 60×50 | ✓ **best result**: predicted_gnd_y [261,252,237]; fitted-in-ROI **constant [41,41,41]**; clip [0,0,1]; no underflow |
| 74479/80 | Launch N=4   | em10, 9 & 20 ms                      | ✗ underflow ~‑5.3 ms **in the launch clock sequence** (same at both budgets ⇒ not the ROI budget)                   |

Calibration found for the red-MOT cloud (side-view Andor, EM-gain mode):
`trap_x_pixel ≈ 205`, `trap_y_pixel ≈ 289` (vs dipole defaults 215/273). A residual
~16 px constant centring offset remains (cloud at ROI-relative 41 vs centre 25) — a
fine-tune of `trap_y_pixel`, tracking is already correct.

## Root cause: prediction-RPC latency (and the recommended fix)

The host predictor runs as a **blocking `@rpc` inside the imaging slack budget**. On this
master the kernel↔worker round trip is **~5–11 ms and highly variable** (worsened by the
`DisplayInjectionMonitors` interleaving on the shared core). Mitigations already applied:

- slice the intent buffers to `num_events` before the RPC (BUFFER_DEPTH=300 → a few) —
  saved ~7.7 ms;
- removed per-shot logging from the hot path (~1 ms);
- off-budget warm-up call (limited benefit — the cost is per-call, not first-call).
  These got the drop working at a 9 ms budget, but it stays marginal, and a long budget is
  not an option: the **fixed fast-kinetics readout frame** (offset 223, height 100) only
  catches the falling cloud up to ~14 ms TOF, so the budget can't simply be raised.

**Recommended fix (the right one): compute the prediction during MOT loading, off the
imaging path.** Move the predict + grabber-program into `before_start_hook` (runs after
DMA recording, with `break_realtime` and huge slack). Parametrise the imaging time as a
fixed `imaging_tof` since release (force it with `at_mu(t_release + imaging_tof)`), and
have the predictor take since-release times computed from params
(`t_pulse_since_release = playback_offset + t_recorded`; `playback_offset` = `expansion_time`
for the red MOT, ≈0). Then the imaging TOF drops to a few ms (cloud near the trap centre,
perfectly framed) and the RPC latency/variance is irrelevant. This also unblocks the
launch (no tight in-shot RPC). Est. ~half a day, wants a careful hardware check.

## Launch status

`RedMOTLaunchDynamicROI_N*` underflows in the **declarative clock launch sequence** from
the red MOT (not the ROI prediction). Needs the LMT-from-red-MOT pulse timing tuned
(OPLL ramps, AOM switch timing, the `pre_experiment_delay`/inter-pulse delays), plus
velocity-slicing commissioning (shelving setpoint/detuning) — hands-on clock work. The
sliced-spectroscopy experiment (`RedMOTSlicedSpecDynamicROI`) was not reached.

## State left for the morning

- Live checkout `/home/stronlab/artiq_stuff/icl_experiments` on `claude/dynamic-roi-red-mot`
  @ `51be077c`, clean tree. Repo rescanned (the 5 experiments are in the explist).
- Monitors (MonitorMaster + DisplayInjectionMonitors) untouched and running; lasers locked.
- `DISABLE_EM_GAIN` was already `false` on the master; EM gain enabled only via per-run
  args (never hard-coded).
- All code committed + pushed to GitLab. Branch ready for review/MR.
