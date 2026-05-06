# Handoff: Migrate FK Imaging to AndorCameraConfig

## Branch: `add_grabber_config`

## Context

This branch migrates fast-kinetics (FK) imaging base classes from old-style
`AndorCameraControl` constructor arguments (broken after `camera_config=` was
made mandatory) to the new `AndorCameraConfig` interface. The overall structure
is that each imaging mixin must implement `get_andor_camera_config_hook()` which
creates and returns an `AndorCameraConfig` fragment, instead of the old
`setup_andor_camera_control_hook()` which directly constructed `AndorCameraControl`.

**pytest command** (use this — `python -m pytest` doesn't work without activating env):

```
/nix/store/x9p92l5j2vpmz5gcyj5wlq5wl28q6yxa-python3-3.10.12-env/bin/pytest
```

## Committed Commits

- `4f602f88` `[AI] Phase 1+2: Add FastKineticsCameraConfig, update AndorCameraControl`

## Modified Files (uncommitted)

### `repository/lib/experiment_templates/mixins/andor_imaging/normalised_fast_kinetics_base.py`

**Status: Modified, NOT committed. Tests not fully passing (but pre-existing failures exist — see below).**

Changes made:

1. Added `NormalisedFKConfig(FastKineticsCameraConfig)` at ~line 100:
    - `num_andor_images=4`, `num_images_per_series=2`, `num_grabber_rois=2`, `num_grabber_readouts=2`
    - `fast_kinetics_num_shots=2`, `fast_kinetics_height_default/offset_default` from constants
    - `build_fragment(x0, y0, x1, y1, excited_shift=0)` creates 4 `roi_xN` IntParams
    - `roi_buffer = np.zeros((self.num_grabber_rois, 4), dtype=np.int32)` — IMPORTANT: must be numpy array, not list-of-lists
    - `_excited_shift = np.int32(excited_shift)` — IMPORTANT: must be int32, not Python int
    - `@portable get_rois()` fills `roi_buffer[0]` and `roi_buffer[1]` using explicit index assignments (no loop — avoids ARTIQ type unification errors)
2. Added `NormalisedFKDoubleTrapConfig(FastKineticsCameraConfig)` at ~line 180:
    - Same structure but `num_grabber_rois=4`, 8 ROI params (fwd_x0/y0/x1/y1, bwd_x0/y0/x1/y1)
    - `@portable get_rois()` fills `roi_buffer[0..3]` with explicit assignments (no loop)
3. `NormalisedFastKineticsBase`: replaced `setup_andor_camera_control_hook()` with `get_andor_camera_config_hook()` returning `NormalisedFKConfig` with ANDOR_ROI_X0/Y0/X1/Y1
4. `NormalisedFastKineticsDoubleTrapBase`: replaced with `get_andor_camera_config_hook()` returning `NormalisedFKDoubleTrapConfig` with ANDOR_ROI_DIPOLE_TRAP_FORWARD/BACKWARD constants
5. Fixed `get_roi_i()` calls in `host_setup()` → `self.andor_camera_config.get_rois()` then `list(rois[i])`
6. Fixed `self.andor_camera_control.slice_from_roi_params(image, grabber_idx)` → `self.slice_from_roi_params(image, self.andor_camera_config.get_rois()[grabber_idx])`

### `repository/lib/experiment_templates/mixins/andor_imaging/normalised_fast_kinetics.py`

**Status: Modified, NOT committed.**

Change: Fixed `NormalisedXXODTFastKineticsBase.get_monitor_rois()`:

- Was: calling `self.andor_camera_control.get_roi_i(0)` and `get_roi_i(2)` (method doesn't exist)
- Now: `rois = self.andor_camera_config.get_rois(); return [list(rois[0]), list(rois[2])]`

## ARTIQ Kernel Constraints (CRITICAL for future phases)

ARTIQ's Python-to-kernel compiler has strict constraints. When writing `@portable` or `@kernel` methods in config classes:

1. **No list comprehensions** — `[[x] * 4 for _ in range(n)]` fails; use `np.zeros((n, 4), dtype=np.int32)` instead
2. **No loop-variable arithmetic** producing type mismatches — i.e., `i * height` where `i` is a Python loop int and `height` is `int32` causes `cannot unify int32 with int64`; avoid loops entirely in kernel code, use explicit `roi_buffer[0][j] = ...; roi_buffer[1][j] = ...`
3. **`_excited_shift` must be `np.int32()`** — otherwise arithmetic with int32 params fails with type unification
4. **`roi_buffer` must be `np.zeros((N, 4), dtype=np.int32)`** — list-of-lists also causes KeyError in ARTIQ embedding

## Pre-existing Test Failures (at HEAD, before any changes)

These tests were already failing before Phase 3a and are NOT our responsibility to fix now:

- `MeasureXXODTFrag`, `MeasureXXODTWithTransparancyFrag`, `StarkBlastXXODTFrag`
- `LoadXXODTMixin`, `LoadXXODTWithTransparencyBeamMixin`
- `NormalisedRedMOTFastKineticsMixin`, `NormalisedDipoleTrapFastKineticsMixin`, `NormalisedXXODTFastKineticsMixin`, `NormalisedXXODTSpectroscopyFastKineticsMixin`
- `SingleImageNormalisedDipoleTrapFastKineticsMixin`
- `TripleImageXXODTFastKineticsMixin`

All the leaf mixin failures are because they still call `get_grabber_roi_defaults()` FIXME — those are Phase 4.

## Still TODO

### Phase 3a — COMMIT

Verify the current state of normalised_fast_kinetics_base.py and normalised_fast_kinetics.py, then commit:

```
git add repository/lib/experiment_templates/mixins/andor_imaging/normalised_fast_kinetics_base.py
git add repository/lib/experiment_templates/mixins/andor_imaging/normalised_fast_kinetics.py
git commit -m "[AI] Phase 3a: Add NormalisedFKConfig classes, update base classes"
```

The tests to check for REGRESSIONS (i.e. things that passed before and should still pass):

```
/nix/store/x9p92l5j2vpmz5gcyj5wlq5wl28q6yxa-python3-3.10.12-env/bin/pytest tests/test_compile_all.py -k "ClockSpecFromXXODTFrag or ClockSpecFromXXODTWithShelving" -q
```

These two passed after Phase 3a but were failing at HEAD. Good sign.

### Phase 3b — `triple_imaging_fast_kinetics_base.py` (197 lines)

File: `repository/lib/experiment_templates/mixins/andor_imaging/triple_imaging_fast_kinetics_base.py`

The `TripleImageFastKineticsBase` class still uses old-style `setup_andor_camera_control_hook()`:

- `num_andor_images=3`, `num_grabber_rois=3`, `num_grabber_readouts=1`
- `fast_kinetics_height_default=constants.ANDOR_FAST_KINETICS_HEIGHT`
- At line 122 still calls `self.setattr_fragment("andor_camera_control", AndorCameraControl, roi_defaults=..., fast_kinetics_height_default=..., fast_kinetics_num_shots=3, ...)`
- FIXME at line 136: `get_grabber_roi_defaults()` returns `calculate_grabber_rois(...)` with `ANDOR_ROI_X0/Y0/X1/Y1`

**Plan**: Create `TripleFKConfig(FastKineticsCameraConfig)` with:

- `num_andor_images=3`, `num_images_per_series=3`, `num_grabber_rois=3`, `num_grabber_readouts=1`, `fast_kinetics_num_shots=3`
- `build_fragment(x0, y0, x1, y1)` — no `excited_shift` (not used in triple imaging)
- `roi_buffer = np.zeros((3, 4), dtype=np.int32)`
- `@portable get_rois()`: fills `roi_buffer[0]`, `[1]`, `[2]` with explicit index assignments:
    ```python
    roi_buffer[0][j] = ...  # i=0 in original formula: y0 + 0*height - offset
    roi_buffer[1][j] = ...  # i=1: y0 + height - offset
    roi_buffer[2][j] = ...  # i=2: y0 + 2*height - offset
    ```
    Note: triple imaging uses `y0 + i * fast_kinetics_height - fast_kinetics_offset` (no excited_shift)

Then update `TripleImageFastKineticsBase`:

- Import `TripleFKConfig` at top of file
- Replace `setup_andor_camera_control_hook()` → `get_andor_camera_config_hook()` returning `TripleFKConfig(x0=ANDOR_ROI_X0, y0=ANDOR_ROI_Y0, x1=ANDOR_ROI_X1, y1=ANDOR_ROI_Y1)`
- Remove `get_grabber_roi_defaults()` FIXME
- Replace `self.andor_camera_control.bind_param(...)` → `self.andor_camera_config.bind_param(...)` (in `build_fragment`)
- Keep everything else the same

### Phase 3c — `single_image_normalised_fast_kinetics_base.py` (905 lines)

File: `repository/lib/experiment_templates/mixins/andor_imaging/single_image_normalised_fast_kinetics_base.py`

Has a different `calculate_grabber_rois()` that also includes background ROIs (`bg_width` param). Three base classes:

- `SingleImageNormalisedFastKineticsBase` (abstract, has `get_andor_camera_config_hook` as abstract method at line 169, FIXME at 170)
- `SingleImageNormalisedFastKineticsSingleTrapBase` at line ~200 — `num_grabber_rois=6` (2 signal + 2×2 bg)
- `SingleImageNormalisedFastKineticsDoubleTrapBase` at line ~350 — `num_grabber_rois=12`

Background ROI formula (from `calculate_grabber_rois`): left BG has `x0-bg_width` to `x0`; right BG has `x1` to `x1+bg_width`

**Plan**: Create `SingleFKSingleTrapConfig(FastKineticsCameraConfig)` and `SingleFKDoubleTrapConfig(FastKineticsCameraConfig)`:

- Each with `build_fragment(x0, y0, x1, y1, excited_shift=0)` (plus fwd/bwd variants for double trap)
- `roi_buffer = np.zeros((N, 4), dtype=np.int32)` where N=6 or 12
- `bg_width = constants.ANDOR_SINGLE_FAST_KINETICS_BACKGROUND_ROI_WIDTH`
- `@portable get_rois()` with explicit index assignments for all 6/12 ROIs
- The ROI order: signal_0, signal_1, bg_left_0, bg_left_1, bg_right_0, bg_right_1 (need to verify against existing `process_grabber_data_hook`)

### Phase 4 — Leaf class FIXMEs

Files:

- `normalised_fast_kinetics.py` lines 65, 130, 266 — `NormalisedDipoleTrapFastKineticsMixin`, `NormalisedXXODTFastKineticsMixin`, `NormalisedXXODTSpectroscopyFastKineticsMixin` — each has `get_grabber_roi_defaults()` FIXME — replace with `get_andor_camera_config_hook()` returning config class with appropriate ROI constants
- `triple_imaging_fast_kinetics.py` lines 60, 99 — `TripleImageDipoleTrapFastKineticsMixin`, `TripleImageRedMOTFastKineticsMixin` — same pattern

These all inherit from base classes that already have `setup_andor_camera_control_hook()` (old style), so each leaf class overrides with `get_grabber_roi_defaults()` to customize ROIs. After Phase 3b/3c, these bases will have `get_andor_camera_config_hook()`, and the leaf classes need to override it instead.

**Pattern per leaf class**:

```python
# OLD (each leaf):
def get_grabber_roi_defaults(self):  # FIXME
    return calculate_grabber_rois(x0=SOME_CONST, ...)

# NEW (each leaf):
def get_andor_camera_config_hook(self):
    f = self.setattr_fragment(
        "andor_camera_config",
        NormalisedFKConfig,  # or TripleFKConfig etc.
        x0=constants.SOME_CONST_X0,
        y0=constants.SOME_CONST_Y0,
        x1=constants.SOME_CONST_X1,
        y1=constants.SOME_CONST_Y1,
    )
    self.andor_camera_config: NormalisedFKConfig
    return f
```

Specific ROI constants needed (already in `repository/lib/constants.py`):

- `NormalisedDipoleTrapFastKineticsMixin`: uses `ANDOR_ROI_DIPOLE_TRAP_FORWARD_SINGLE_IMAGE_*` with `excited_shift=constants.ROI_SHIFT_EXCITED_STATE`
- `NormalisedXXODTFastKineticsMixin`: uses forward + backward dipole trap ROIs (as NormalisedFKDoubleTrapConfig)
- `NormalisedXXODTSpectroscopyFastKineticsMixin`: same as XXODT but with spectroscopy
- `TripleImageDipoleTrapFastKineticsMixin`: uses dipole trap ROIs
- `TripleImageRedMOTFastKineticsMixin`: uses ANDOR_ROI_X0/Y0/X1/Y1

### Phase 5 — Simplify process_grabber_data_hook (OPTIONAL)

`single_image_normalised_fast_kinetics_base.py` has ~50 lines in `process_grabber_data_hook` that access `self.andor_camera_control.roi_N_xN.get()` to reconstruct ROI areas. After Phase 3c, these can be simplified to `rois = self.andor_camera_config.get_rois(); area = (rois[i][2]-rois[i][0]) * (rois[i][3]-rois[i][1])`.

### Final TODO

After all phases complete:

```
git fetch origin worktree-cleanup_pre_trigger
git merge origin/worktree-cleanup_pre_trigger
```

### Verification

```bash
grep -r "get_grabber_roi_defaults\|roi_defaults=" repository/ | grep -v ".pyc"
# Should return nothing

/nix/store/x9p92l5j2vpmz5gcyj5wlq5wl28q6yxa-python3-3.10.12-env/bin/pytest tests/test_compile_all.py -q
```
