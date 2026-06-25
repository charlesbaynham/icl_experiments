# LMT-compensated dynamic ROI: code review & operator validation plan

Date: 2026-06-12

## Scope

This document covers the code that dynamically repositions the Andor camera
ROIs according to the LMT (large momentum transfer) clock-pulse sequence that
has occurred in a shot. The feature has never been run in the lab. It contains:

1. Where the code lives and how it is supposed to work.
2. A completeness assessment ("is it nominally finished?" — **no**, see below).
3. Static-analysis findings (bugs that must be fixed before any lab time is
   spent).
4. A progressive, operator-driven test campaign to validate the feature on the
   real experiment.

## 1. Where the code lives

| Component                                          | Location                                                                                                                                                                                                                     |
| -------------------------------------------------- | ---------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| Ballistic trajectory predictor (host-side physics) | `repository/lib/physics/ballistic.py`                                                                                                                                                                                        |
| Dynamic camera config + imaging mixin              | `repository/lib/experiment_templates/mixins/andor_imaging/lmt_compensated_normalised_imaging.py` (`LMTCompensatedCameraConfig`, `NormalisedFastKineticsLMTCorrectedMixin`)                                                   |
| Pulse sequence recording (feeds the predictor)     | `repository/lib/fragments/pulse_recorder_and_tracker.py` (`PulseDMARecording.register_pulse`), called from the LMT mixins in `repository/lib/experiment_templates/mixins/LMT_launch_mixins.py` and `clock_interferometry.py` |
| Predictor unit tests                               | `tests/test_ballistic_predictor.py` (13 tests, all currently `xfail`)                                                                                                                                                        |
| Grabber ROI programming                            | `repository/lib/fragments/cameras/andor_camera.py` (`AndorCameraControl.device_setup`)                                                                                                                                       |

Intended data flow per shot:

1. `DMA_record_hook` records `actions_after_drop()` (drop, launch, LMT pulses)
   into DMA at the start of `run_once`. While recording, each clock pulse calls
   `register_pulse()`, which stores start time, duration and direction;
   `post_dipole_trap_hook` stamps `t_dipole_beams_off` (atom release = t₀).
2. The sequence is played back via `dma_recording_fragment.playback()`.
3. At imaging time, `NormalisedFastKineticsLMTCorrectedMixin.do_imaging_hook_andor`
   calls `calculate_atom_positions(t1, t2, …)`, which RPCs to the host where
   `predict_positions_from_mu` integrates gravity + photon-recoil kicks and
   projects onto the sensor via `CameraGeometry`.
4. `LMTCompensatedCameraConfig.get_rois()` builds two ROIs centred on the
   predicted ground (shot 1, t₁) and excited (shot 2, t₂) cloud positions.

## 2. Completeness assessment — NOT nominally finished

**The core physics function is not implemented.** `predict_position()` in
`ballistic.py` unconditionally raises `NotImplementedError`, preceded by the
author's comment `# TODO This logic is totally wrong` (lines 171–172). All 13
unit tests in `tests/test_ballistic_predictor.py` are marked
`xfail(reason="Ballistic predictor not implemented yet")` (verified: 13
xfailed). Every shot using this feature would crash at the first imaging RPC.

Additionally, **no concrete experiment instantiates
`NormalisedFastKineticsLMTCorrectedMixin`** anywhere in the repository, so the
code has never even been compile-checked by `test_compile_all.py` (which only
compiles fragments that exist as experiments). The kernel-side code paths are
entirely unexercised.

## 3. Static-analysis findings

Ordered roughly by severity. F1–F6 are hard blockers; the feature cannot work
at all until they are fixed.

### F1 — Predictor unimplemented / physics model wrong (blocker)

`ballistic.py:171`. As above. Note the dead code below the `raise` models
"ground = no kicks, excited = all kicks". That is not how an LMT sequence's
output ports work: in an interferometer/launch sequence _both_ detected ports
receive most of the momentum kicks; the ports typically differ by ~1 photon
recoil, and atoms swap internal state at each π pulse (so "is_up" alone does
not determine the kick sign experienced by a given port). The model must be
re-derived against the actual sequences in `LMT_launch_mixins.py` before
implementation. This is presumably what the author's TODO means.

### F2 — `LMTCompensatedCameraConfig` cannot be constructed (blocker)

`lmt_compensated_normalised_imaging.py:52–53` sets
`fast_kinetics_height_default` / `fast_kinetics_offset_default`, but the base
class `FastKineticsCameraConfig.__init__` (`andor_camera.py:140–145`) requires
class attributes named `fast_kinetics_height` / `fast_kinetics_offset` and
raises `ValueError` when they are `None`. Nothing reads the `*_default` names.
Instantiating the fragment crashes immediately.

### F3 — `get_rois` is `@kernel` but is called from the host (blocker)

The base contract (`AndorCameraConfig.get_rois`) is `@portable`; the sibling
configs (`NormalisedFKConfig`, `NormalisedFKDoubleTrapConfig`) honour that. The
LMT version is decorated `@kernel`, yet it is called from host context in at
least three places: `AndorCameraConfig.host_setup` (`andor_camera.py:76–84`),
`NormalisedFastKineticsBase.host_setup` (applet defaults,
`normalised_fast_kinetics_base.py:371`) and the `@host_only`
`do_gauss_fit_hook`. Calling a `@kernel` from host triggers a separate
core-device kernel run per call. Worse, `roi_buffer`, `gnd_x` etc. are only
assigned _after_ `super().host_setup()` returns
(`lmt_compensated_normalised_imaging.py:194–202`), so the very first host call
references attributes that don't exist yet. Fix: decorate `@portable`,
allocate `roi_buffer` in `build_fragment` (as the siblings do), and initialise
`gnd_*`/`excited_*` before calling `super().host_setup()`.

### F4 — Timebase mismatch between pulse record and image times (blocker)

`t_dipole_beams_off` and all `_pulse_record_*_mu` timestamps are captured
_inside_ `core_dma.record()`. ARTIQ's `DMARecordContextManager.__enter__`
resets `now` to **zero** for the duration of the recording
(`vendor/artiq/artiq/coredevice/dma.py`), so these are recording-relative
times (t₀ ≈ 0). But `do_imaging_hook_andor`
(`lmt_compensated_normalised_imaging.py:350–352`) takes `t1_mu = now_mu()` on
the **live** timeline and passes the recording-relative `t_zero_mu` alongside
it. The computed free-fall time `(t1 − t₀)·ref_period` is therefore an
absolute-timeline value — hours, growing every shot — not the physical drop
time. Pulse times relative to t₀ are mutually consistent; only the image
times are broken. Fix: capture `now_mu()` immediately before
`dma_recording_fragment.playback()` (the playback offset), and compute image
times in the same recording-relative frame, e.g.
`t1_rel = t1_live − t_playback_start`, since DMA playback replays recorded
event times offset by `now_mu()` at the playback call.

### F5 — Grabber ROIs are programmed before the positions are computed (blocker)

`AndorCameraControl.device_setup` (`andor_camera.py:515–533`) writes the
grabber ROI registers at the start of each shot using `get_rois()`.
`calculate_atom_positions` only runs later, inside the imaging hook. Updating
`gnd_*`/`excited_*` at that point does **not** reprogram the grabber, so the
ROIs actually in effect are those computed in the _previous_ shot (trap centre
on the first shot). In a scan over LMT parameters every point is measured with
the previous point's ROIs. Since `DMA_record_hook` runs at the very start of
`run_once`, the pulse record is already complete before playback: compute the
positions right after recording and re-issue `grabber.setup_roi(...)` (or move
the calculation so it precedes `device_setup`'s ROI programming). This also
resolves F8.

### F6 — Fast-kinetics readout geometry ignored in `get_rois` (blocker)

Sibling configs subtract `fast_kinetics_offset` from the y coordinates and add
`(fast_kinetics_height − excited_shift)` to the second shot's ROI
(`normalised_fast_kinetics_base.py:129–147`), because in FK mode the second
exposure is shifted down the readout frame by the FK subarea height. The LMT
`get_rois` uses raw sensor coordinates for both ROIs: the ground ROI is
misplaced by `−offset` and the excited ROI is additionally missing the
`+height` FK row shift (the _physical_ inter-shot movement is handled by the
predictor; the _readout_ shift is not). The `2 × sensor_height` y-clamp shows
the double-height FK frame was considered, but the shift itself was never
applied.

### F7 — Camera tilt parameters are unusable as exposed

`build_fragment` exposes the nine axis components as freely-editable
`FloatParam`s "so that small unknown tilts can be corrected without code
changes", but `CameraGeometry.__post_init__` (`ballistic.py:82–104`)
_validates_ (unit norm and pairwise orthogonality to 1e-6) rather than
normalising/orthogonalising. Almost any hand-entered tilt (e.g. nudging
`optical_axis_y` to 0.999) makes the mid-experiment RPC raise `ValueError`.
Fix: normalise and re-orthogonalise (Gram–Schmidt) in `__post_init__`, or
re-parameterise as two tilt angles.

### F8 — Synchronous RPC at imaging time risks RTIOUnderflow

`calculate_atom_positions` is a blocking RPC issued immediately before the
first fluorescence pulse, which itself writes events _into the past_ (camera
pre-trigger + FK shift time, `andor_camera.py:617–624`). No slack is added.
A millisecond-scale RPC round trip right at that point is a realistic
underflow source. Moving the calculation to just after DMA recording (per F5)
hides the latency in the MOT-loading part of the shot.

### F9 — No compile coverage

Nothing uses the mixin, so `test_compile_all.py` never compiles it. Add a
concrete test fragment under `repository/tests/` so kernel compilation of the
whole chain (mixin + config + RPC signatures) is checked in CI.

### F10 — Degenerate ROIs not guarded (minor)

If a predicted position falls off-sensor, `min`/`max` clamping can produce
`x1 < x0` (negative area; `calculate_area_from_roi` goes negative and the
means flip sign). Clamp so `x0 ≤ x1`, `y0 ≤ y1` and surface a flag/warning
when an ROI was clipped — during validation this is a key diagnostic.

### F11 — Magnification placeholder (calibration risk, not a code bug)

`ANDOR_CAMERA_FACTS["magnification"] = 1` (`constants.py:41`) is the
metres→pixels scale for _all_ predicted displacements. If the real imaging
magnification differs, every prediction is scaled wrongly. Stage 4 below
calibrates this empirically before any LMT validation is attempted.

## 4. Prerequisites before lab time (Stage 0 — desk work)

No operator time should be spent until all of these are green:

- [ ] Derive the correct port-trajectory model for the actual LMT sequences
      (which pulses kick which port, signs for up/down beams) and implement
      `predict_position` (F1). Update the unit tests to the agreed model and
      remove the module-level `xfail`.
- [ ] Fix F2–F8 as described above.
- [ ] Add a concrete test experiment (F9) and confirm it passes the relevant
      `test_compile_all.py` selector.
- [ ] `pytest tests/test_ballistic_predictor.py` fully green, including new
      tests for: free fall in each camera frame, single up/down kicks, kick at
      pulse centre, both output ports of a representative N-pulse LMT
      sequence, and the mu-conversion wrapper.

Useful sanity numbers for everything below (Sr-87, 698 nm clock, 16 µm pixels,
magnification 1):

- Recoil velocity v_r = h/(mλ) ≈ **6.6 mm/s** → ≈ 4.1 px displacement per
  recoil after 10 ms.
- Free fall ½gt²: 10 ms → 0.49 mm ≈ **31 px**; 20 ms → ≈ 123 px; 30 ms →
  ≈ 276 px (off a 100 px ROI well before 30 ms).
- Between the two FK shots (3.5 ms apart) at 10 ms drop the cloud falls
  ≈ 0.34 mm ≈ **21 px** — this is what the old static `excited_shift`
  parameter approximated and the predictor must reproduce.

## 5. Operator validation campaign

Each stage has explicit pass criteria; do not proceed to the next stage until
the current one passes. Record outcomes (dataset RIDs, screenshots of the
`Ground/Excited bg corrected` applets, fitted numbers) in the lab book under a
"dynamic ROI validation" heading.

### Stage 1 — Dry run on hardware, no atoms

**Purpose:** prove the plumbing (construction, host_setup, kernel compile, RPC,
grabber programming) without needing atoms.

1. Block the MOT (e.g. blue shutter closed) or run at a time with no atom
   signal. Run the new concrete experiment once with default parameters and
   `num pulses = 0`.
2. Confirm: no crash in `host_setup`, no kernel compile errors, no
   `RTIOUnderflow`, the shot completes and produces the usual 4 Andor images.
3. Add (temporarily) a log/dataset that records the four ROI rectangles
   actually programmed into the grabber each shot, plus the predicted
   (x, y) for ground and excited. Confirm the ROIs are sane: inside the
   frame, correct width/height, excited ROI = ground ROI + FK height row
   shift when no pulses and short drop.
4. Inspect the `pulse_record` dataset for a shot with a real LMT sequence
   configured (still no atoms): number of pulses, directions and start times
   must match the programmed sequence (cross-check against the sequence
   parameters; times relative to t₀ should match the DMA timeline by
   construction).
5. Measure slack around the position-calculation RPC (e.g. log
   `core.mu_to_seconds(now_mu() - core.get_rtio_counter_mu())` before/after).
   **Pass:** ≥ 1 ms slack margin remains at the first camera trigger over 50
   consecutive shots; ROI rectangles and pulse record all correct.

### Stage 2 — Static equivalence with atoms (no LMT pulses, short drop)

**Purpose:** show the dynamic-ROI experiment reproduces the trusted static-ROI
experiment when nothing moves.

1. Run the existing static experiment (`NormalisedFKConfig`-based, e.g. the
   current clock spectroscopy readout) on resonance with a normal short drop.
   Record excitation fraction and atom number over ≥ 50 shots.
2. Run the dynamic-ROI experiment with identical sequence parameters,
   `num pulses = 0`, and `trap_x/y_pixel` + `roi_width/height` chosen so the
   computed ROI rectangle is numerically identical to the static config's
   (verify via the Stage-1 ROI logging).
3. **Pass:** mean excitation fraction and atom number agree with the static
   experiment within their shot-to-shot scatter (same mean within 1σ of the
   standard errors; comparable scatter). The bg-corrected applet images look
   identical.

### Stage 3 — Free-fall tracking and camera-geometry calibration

**Purpose:** validate (and calibrate) gravity direction, sensor axes signs and
the metres→pixels scale before any recoil physics is involved.

1. Still `num pulses = 0`. Enable `do_gauss_fit` and `save_raw_andor_image`.
   Scan the drop time (dipole release → imaging) from ~2 ms to ~25 ms.
2. For each point compare the _fitted_ cloud centre (`x_pos_0_ground`,
   `y_pos_0_ground` channels, plus the raw-image fits) with the _predicted_
   ROI centre (from the Stage-1 logging).
3. Fit the measured centre-vs-t² slope to extract the empirical pixels-per-
   metre scale and the apparent gravity direction on the sensor. Update
   `ANDOR_CAMERA_FACTS["magnification"]` (F11), `trap_x/y_pixel` defaults and,
   if a residual transverse drift is visible, the camera axis tilts (after the
   F7 fix makes them usable).
4. Re-run the scan with calibrated values.
   **Pass:** predicted vs fitted centre agrees to **≤ 3 px** at every drop
   time up to 20 ms, in both x and y, and the cloud stays comfortably inside
   the ROI (capture check: ROI sum / full-frame fitted amplitude ratio flat
   across the scan).

### Stage 4 — Single-pulse recoil: sign and magnitude

**Purpose:** first test of the kick model, where the answer is unambiguous.

1. Configure a single π pulse on the **up** beam shortly after release, with a
   drop long enough that one recoil ≈ 4–8 px at imaging (≥ 10 ms after the
   pulse). Use velocity selection / shelving as in normal operation so the two
   FK shots correspond to the two ports.
2. Compare the fitted positions of both ports against prediction. The
   excited-port image must be displaced along the clock beam direction by
   v*r·(t_image − t_pulse) relative to the unkicked trajectory; check the
   \_sign* on the sensor matches.
3. Repeat with a single **down**-beam pulse: displacement must flip sign.
4. Move the pulse earlier/later in the drop and confirm the displacement
   scales as (t_image − t_pulse).
   **Pass:** sign correct for both beams; magnitude within 20 % (limited by
   cloud-fit precision at ~1 recoil); time-of-pulse scaling linear.

### Stage 5 — Full LMT sequences, increasing momentum transfer

**Purpose:** validate the complete predictor against real LMT sequences and
confirm the ROIs actually capture the clouds where static ROIs would fail.

1. Run the standard LMT launch/interferometry sequence at small N (e.g. 2
   recoils) with full-frame saving and Gaussian fits on. Compare fitted vs
   predicted centres for both ports.
2. Step N up progressively (2 → 4 → 8 → maximum routinely used). At each N:
    - predicted vs fitted centre for both ports;
    - capture fraction (ROI sum vs full-frame fit) — must not degrade with N;
    - excitation fraction vs the static-ROI experiment at the largest N where
      static ROIs are still usable — values must agree.
3. Scan `delay_between_imaging_pulses` (t₂ handling) at fixed N and confirm
   the second-shot prediction tracks.
4. Deliberately push one port near the sensor edge (large N / long drop) and
   confirm the F10 clamping behaviour: a clipped-ROI warning, no negative
   areas, no crash.
   **Pass:** ≤ 5 px prediction error for both ports at all N; capture
   fraction flat in N; excitation fraction consistent with the static
   reference where comparable.

### Stage 6 — Operational acceptance

**Purpose:** confidence for unattended use.

1. Run a realistic physics scan (the one this feature was built for) overnight
   with the Stage-1 ROI/prediction logging still enabled.
2. Next morning check: zero RTIOUnderflows, zero clipped-ROI warnings (unless
   expected), prediction-vs-fit residuals stable over the run (no drift —
   if the trap position drifts, that is a calibration-maintenance issue to
   document, not a code bug).
3. Remove or demote the temporary logging to debug level, update this plan
   with results, and record the final calibration constants in
   `constants.py` with a dated comment.
   **Pass:** full unattended run with stable residuals; feature signed off
   for production use.

### Troubleshooting quick reference

- **Cloud absent from both ROIs, present in full frame** → check timebase
  (F4 fix) first: a wrong free-fall time is the most likely failure and
  produces grossly misplaced ROIs.
- **Ground port fine, excited port empty** → FK row shift (F6) or kick-model
  sign (Stage 4) — distinguish by whether the offset is ≈ FK height (readout)
  or scales with N/drop time (physics).
- **ROIs correct in the log but data looks like last shot's geometry** →
  ROI programming order (F5) regression.
- **Intermittent `ValueError` from the RPC after touching tilt params** → F7.
- **`RTIOUnderflow` at the first camera trigger** → F8; move the RPC earlier
  or add slack.

## 6. Fix vs rewrite assessment

Question raised after review: is this code unsalvageable — would implementing
from scratch be cheaper than fixing it? Assessment: **no, but only because the
salvage value is very uneven across components.** Recommended approach:
_rewrite the two broken leaves, keep the tree._

### Worth keeping (battle-tested or close to it)

- **Pulse recording machinery** (`PulseDMARecording`, `register_pulse`, the
  tracked-frequency plumbing). Wired into all the LMT mixins, archives to
  datasets with dedup checksums, already in production use for the
  pulse-record output. Probably the largest chunk of work in the feature and
  it needs zero changes.
- **The architecture.** Record the sequence into DMA at the start of the shot
  → timings known in advance → host-side RPC predicts positions → camera
  config builds ROIs. The `actions_after_drop` docstring states this design
  exists specifically so ROIs can be computed in advance — the architecture
  _anticipates_ the fix for F5; the implementation just didn't follow through.
- **The scaffolding in `ballistic.py`**: `CameraGeometry`, `BallisticConfig`,
  the mu-conversion wrapper, and the 13 unit tests with sensible expected
  values. The dataclasses and projection code are fine.

### Genuinely needs rewriting

- **The predictor body** — never written, so there is nothing to salvage or
  fight with. Delete the dead "ground = no kicks, excited = all kicks" code
  below the `raise` rather than patching it.
- **`LMTCompensatedCameraConfig` + the mixin** — where F2–F6 and F8 all live,
  ~150 lines total. Rewrite fresh against the `NormalisedFKConfig` conventions
  (which handle the FK geometry correctly); roughly a day of work.

### Why "from scratch" doesn't help

"Implement from scratch" and "fix" converge on nearly the same task list.
Either way one must (a) derive the correct port-trajectory physics for the
actual LMT sequences — the hard, irreducible part, identical in both
scenarios — and (b) write a correct ~350 lines of predictor + camera config.
A true from-scratch rewrite would _additionally_ redo the pulse recorder and
the test suite, i.e. throw away the best parts. The timebase mismatch (F4)
looks architectural but is a few-line fix (capture `now_mu()` immediately
before `playback()` and rebase) — it only looks scary because the lab symptom
would have been incomprehensible.

Where the "unsalvageable" instinct is right: do **not** minimally patch the
existing lines one finding at a time. The author stopped mid-thought (the
TODO says so), and patching half-finished code line-by-line costs more than
rewriting the affected files cleanly.

**Cost estimate either way:** ~1 day for the integration layer, plus the
physics derivation — which is the same effort in both scenarios and so should
not drive the fix-vs-rewrite decision.
