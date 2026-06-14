# Declarative-LMT clock-sequence RTIOUnderflow from the red MOT — diagnosis, fix & hardware handover

Date: 2026-06-13
Branch: `claude/lmt-clock-underflow-red-mot-ruusiq`
(based on `claude/dynamic-roi-red-mot` @ `8474aa3f` — the dynamic-ROI stack was
merged into this branch so the red-MOT declarative experiments and engine are
present; the underflow fix is layered on top.)

**Status: code fix written + reasoned + host-validated as far as the sandbox
allows. NOT yet compiled against the core device and NOT yet run on hardware
(no Nix/GitLab access and no hardware in this environment). The remaining
steps are the lab compile-check + the on-hardware commissioning below.**

---

## TL;DR

`RedMOTLaunchDynamicROI_N{2,4,8}` and `RedMOTSlicedSpecDynamicROI` throw an
`RTIOUnderflow` (~ -5.3 ms) inside the DMA-played-back clock sequence, while
`RedMOTDropDynamicROI` runs fine. Root cause: **`expansion_time` defaults to
`0`, so the DMA playback of the recorded clock sequence starts with no RTIO
slack**; the recorded clock sequence contains events scheduled at-or-before the
playback cursor (e.g. `prepare_clock_delivery_aom`'s `delay(-clock_delivery_preempt_time)`,
plus the tight OPLL/`at_mu` pulse anchoring), which then fire in the past →
underflow. The pure-drop sequence has no such events (its recording is just a
free-fall marker), which is exactly why it is immune.

Fix: insert a bounded **slack pre-roll** immediately before the DMA playback
(`DeclarativeLMTRedMOTBase.pre_playback_hook`, default 8 ms) and fold it into
the gravity-Doppler reference (`get_doppler_t_ref_mu`). The dynamic-ROI
predictor already keys off the live `get_t_release_mu`/`get_t_playback_start_mu`
anchors (both stamped *after* the pre-roll), so the physics stays consistent.

---

## How the underflow was localised (sandbox, static analysis)

1. **Split: drop works, launch/spec underflow.** The only difference is the
   contents of `lmt_sequence` (SetPoints + clock pulses + clearouts). So the
   underflow is in the recorded clock sequence, not the ROI prediction
   (consistent with the overnight finding that it was identical at 9 ms and
   20 ms ROI budgets).

2. **Recording cannot underflow.** `core_dma.record()` has no real-time
   deadline — it captures events into a buffer. `RTIOUnderflow` (as opposed to a
   sequence error) can therefore only be raised during **playback**.

3. **Slack into playback ≈ `expansion_time`.** In `RedMOTWithExperimentBase.run_once`
   the cursor is reset to light-off (`at_mu(t_light_off_mu)`) and then advanced
   by `delay(expansion_time)` before `do_experiment_after_red_mot_hook` →
   `playback()`. `delay()` advances the timeline cursor without waiting, so it
   builds ~`expansion_time` of slack. **`expansion_time` defaults to `0.0`**
   (`red_mot_experiment.py`), and the overnight runs used `args={}` → **zero
   slack at playback**.

4. **The recorded clock sequence writes into the past.** With zero slack, any
   event scheduled before the playback cursor underflows. Confirmed
   past-writes inside `actions_after_drop` for the launch/spec sequences:
   - `prepare_clock_delivery_aom()` (`clock_spectroscopy.py`): `delay(-clock_delivery_preempt_time)`
     (200 µs) then `at_mu(t_start)` — a documented "writes into the past".
   - `_fire_pulse` programs the OPLL DRG (`stop_ramp` + `start_ramp`, ~5 SPI
     register writes + 2 `io_update` pulses) and then `at_mu(t_start)` with
     `t_start` computed *before* those writes — usually still forward (~7 µs
     SPI < 10 µs budget) but fragile and slack-eating with zero headroom.
   The legacy from-XODT launch (`LMT_launch_mixins.fire_lmt_pulse`) keeps the
   per-pulse DRG programming **commented out** and runs after a long
   evaporation rich in `break_realtime`s, i.e. it both does less per-pulse SPI
   *and* plays back with plenty of slack — which is why it never hit this.

5. **Why ~ -5.3 ms and not -200 µs?** The reported slack is how far the failing
   event is in the past, i.e. roughly `(largest past-reach) - (slack at
   playback)`. With ~0 (or slightly negative, from the real-time red-MOT tail)
   slack, the deficit is dominated by the real-time tail, not a single 200 µs
   write. The exact figure is environment-dependent; the fix makes it
   irrelevant by guaranteeing positive slack. **Capturing the precise failing
   channel/event on hardware (overnight step 1) is still worth doing to confirm
   — see "Verification" below.**

### Things ruled out (so the lab does not re-chase them)
- **Clearout shutters.** The clearout uses `ImagingFluorescencePulse`
  (`blue_imaging_switch` + `blue_imaging_delivery`), both **unshuttered**, so the
  `delay(-shutter_delay)` (5 ms `SRS_SHUTTER_DELAY`) path in
  `ControlBeamsWithoutCoolingAOM.turn_beams_on` is **not** exercised by the
  clearout. (It was an attractive 5 ms ≈ 5.3 ms red herring — the 5 ms shutters
  belong to the blue-MOT beams, not the imaging/clearout beam.)
- **Clock delivery / clock switch / OPLL beams** are all unshuttered.
- **Per-pulse clock firing nets *forward* slack** (the `at_mu(now+10µs)` after
  ~7 µs of SPI), so the dense ladder does not itself exhaust slack.

---

## The fix (committed on this branch)

All changes are local to the red-MOT declarative path; the dipole declarative
path and the legacy stack are untouched.

1. `repository/lib/constants.py`
   - New `LMT_DMA_PLAYBACK_PREROLL = 8e-3` with a comment explaining the slack
     trade-off.

2. `repository/lib/experiment_templates/red_mot_dma_experiment.py`
   - `do_experiment_after_red_mot_hook` now calls a new chainable
     `pre_playback_hook()` (live, slack-rich) *before* stamping
     `t_playback_start_mu` and playing back. Default `pre_playback_hook` is a
     no-op (so `RedMOTDropDynamicROI`, which does not derive the declarative
     base, is unchanged). Named-sub-hook pattern is used because ARTIQ kernels
     do not support `super()`.

3. `repository/lib/experiment_templates/mixins/declarative_lmt.py`
   - `DeclarativeLMTRedMOTBase.build_fragment` spawns a scannable
     `lmt_dma_playback_preroll` param (default `LMT_DMA_PLAYBACK_PREROLL`).
   - `pre_playback_hook` overridden to `delay(lmt_dma_playback_preroll)` →
     rebuilds slack for the playback.
   - `get_doppler_t_ref_mu` now returns
     `-seconds_to_mu(expansion_time + lmt_dma_playback_preroll)` so every
     pulse's gravity-Doppler term stays correct despite the extra
     time-of-flight.

Why this is physically safe: the pre-roll is real free-fall before the
sequence, but (a) it is folded into the Doppler reference, and (b) the
dynamic-ROI predictor reads the actual `get_t_release_mu`/
`get_t_playback_start_mu` stamps (the latter is stamped *after* the pre-roll),
so the recorded-pulse-to-live-time rebasing and the ROI trajectory remain
correct. There is genuinely no way to add playback slack without adding
time-of-flight here (slack = cursor − wall-clock, and the cursor is pinned to
`t_release + expansion_time` by the physics), so a known, Doppler-corrected
pre-roll is the right lever.

### Caveat to watch on hardware
The fixed fast-kinetics readout frame only catches the falling cloud out to
~14 ms TOF (overnight notes). 8 ms of pre-roll + `expansion_time` + the
in-sequence time must leave the cloud inside that frame for `RedMOTSlicedSpec`
(no launch) in particular. **Tune `lmt_dma_playback_preroll` *down* toward the
measured slack deficit once it runs** (see below) to minimise added TOF; the
launch experiments push the cloud up, so they are less sensitive.

---

## What was validated here, and what was NOT

Validated (sandbox):
- Python syntax of all three edited files.
- `repository.lib.constants` imports and exposes `LMT_DMA_PLAYBACK_PREROLL = 0.008`.
- The N4 `lmt_sequence` still compiles via `compile_sequence` (9 events, final
  population `('e', 5)` = 1 slice kick + 4 ladder rungs — correct).
- Edits follow existing patterns exactly (`super().build_fragment()` in a host
  `build_fragment`; `@portable` getter reading param `.get()`s; no-op kernel
  sub-hook override).

NOT validated (needs the lab):
- **Core-device kernel compile.** The Nix dev shell needs a private GitLab
  input (`andor_windows_ndsp`) that is unreachable here, and the full host
  import chain pulls in lab-only device drivers (`tenma_power_supply`, …).
  Run in the lab:
  ```
  nix develop -c python -m pytest \
    "tests/test_compile_all.py::test_build_all_fragments[repository.LMT.red_mot_dynamic_roi / RedMOTLaunchDynamicROI_N4Frag]"
  ```
  (and `_N2Frag`, `_N8Frag`, `RedMOTSlicedSpecDynamicROIFrag`,
  `RedMOTDropDynamicROIFrag`). This compiles the new `pre_playback_hook` /
  `get_doppler_t_ref_mu` kernels.

---

## On-hardware verification & commissioning (deferred — needs Charles's
explicit per-instance authorization to drive hardware; EM gain is OFF by
default — pass `em_gain_enabled=True`, level ~10–30 for the dim sliced/launched
cloud, gain 1 for the bright full cloud)

Use the HEAD-hack loop from the overnight notes (edit+commit+push here; in the
live checkout `git fetch && checkout/pull` this branch; `scan-repository` only
when experiment files change; submit via the artiq-http MCP, `log_level=20`,
never DEBUG — it perturbs timing).

1. **Confirm the fix removes the underflow.** Submit `RedMOTLaunchDynamicROI_N4`
   with `args={}` (so `expansion_time=0`, `lmt_dma_playback_preroll=8 ms`). It
   should now run without `RTIOUnderflow`.
   - If it still underflows, the deficit is > 8 ms: raise
     `lmt_dma_playback_preroll` (e.g. 12–16 ms) until it clears, then proceed.

2. **(Optional, confirms the diagnosis & lets you minimise TOF) Measure the
   actual slack deficit.** The cleanest read without DMA is to temporarily set
   `lmt_dma_playback_preroll` to a few values (e.g. 2, 4, 6, 8 ms) and find the
   threshold at which the underflow disappears — that threshold ≈ the deficit.
   Set the working pre-roll ~1–2 ms above it and update the
   `LMT_DMA_PLAYBACK_PREROLL` default if you like.

3. **Commission velocity slicing.** With the underflow gone, scan the slice
   (the first `SetPoint(setpoint=CLOCK_SHELVING_PULSE_SETPOINT, …)` +
   `pi(Beam.UP, m=0, 'slice')`):
   - Scan `p00_setpoint_slice` (the slice `SetPoint`'s spawned setpoint param)
     to find the intensity giving the intended slicing Rabi frequency; update
     the declared `rabi_up`/default once found.
   - Scan the slice pulse's detuning-offset param to centre on the v=0 class.
   - Confirm a launched cloud appears for `RedMOTLaunchDynamicROI_N4` (EM gain
     ~10–30). Then `N2`/`N8`.

4. **Confirm the dynamic ROIs track the launched cloud** across N (already
   validated for drops at RID 74478; the predictor is intent-driven and
   unchanged here). Check `clip` flags and the fitted-in-ROI position stays
   roughly constant as the cloud moves.

5. **`RedMOTSlicedSpecDynamicROI`** — watch the FK-frame caveat above; reduce
   the pre-roll / adjust `expansion_time` if the (un-launched) cloud falls out
   of the readout frame.

---

## Files changed
- `repository/lib/constants.py` (+`LMT_DMA_PLAYBACK_PREROLL`)
- `repository/lib/experiment_templates/red_mot_dma_experiment.py`
  (`pre_playback_hook` seam)
- `repository/lib/experiment_templates/mixins/declarative_lmt.py`
  (`DeclarativeLMTRedMOTBase`: param + pre-roll + Doppler-ref correction)

## Note for review
This branch contains the whole `claude/dynamic-roi-red-mot` stack (merged in so
the red-MOT declarative experiments exist to fix). If that branch lands
separately, this fix is the small diff on top (the three files above).
