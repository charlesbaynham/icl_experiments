# Plan: Migrate FK Imaging Classes to `AndorCameraConfig` Interface

**The core problem:** `AndorCameraControl.build_fragment()` was already updated to require a `camera_config` arg — but the 4 fast-kinetics base classes still call it with the old `roi_defaults=`, `fast_kinetics_height_default=`, `fast_kinetics_offset_default=`, and `fast_kinetics_num_shots=` args. These calls are currently broken. The FIXMEs mark all the places that need updating.

**Recommended approach:** Create `AndorCameraConfig` subclasses for each FK family, move all FK params (including `fast_kinetics_time_between_shots`) into those configs, and have the base classes use `get_andor_camera_config_hook()` like `BGCorrectedAndorImage` already does.

---

## Steps

### Phase 1 — Add `FastKineticsCameraConfig` intermediate base (`andor_camera.py`)

Create `FastKineticsCameraConfig(AndorCameraConfig)` between `AndorCameraConfig` and the concrete FK configs. This is the only new class needed in `andor_camera.py` — `AndorCameraConfig` itself stays unchanged.

`FastKineticsCameraConfig`:

- Class attrs: `fast_kinetics_height_default: int`, `fast_kinetics_offset_default: int`, `fast_kinetics_num_shots: int` (all abstract — subclasses must set them)
- In `build_fragment()`: creates IntParams `fast_kinetics_height` (default from class attr) and `fast_kinetics_offset` (default from class attr), and a FloatParam `fast_kinetics_time_between_shots` (default 3.5 ms). Type annotations: `fast_kinetics_height: IntParamHandle`, `fast_kinetics_offset: IntParamHandle`, `fast_kinetics_time_between_shots: FloatParamHandle`
- Static method `_calculate_rois(height, offset, num_images, x0, y0, x1, y1, excited_shift=0)` — implements the simple FK ROI formula (no background ROIs). Used by NormalisedFK and TripleFK families.

### Phase 2 — Update `AndorCameraControl` (`andor_camera.py`) — _depends on Phase 1_

Remove FK constructor args, read them from the config instead:

- Remove `fast_kinetics_height_default`, `fast_kinetics_offset_default`, `fast_kinetics_num_shots` from `build_fragment()` signature
- Read `self.fast_kinetics_num_shots = camera_config.fast_kinetics_num_shots` (from config class attr)
- Derive `self.fast_kinetics_mode = self.fast_kinetics_num_shots > 1`
- Remove the `fast_kinetics_height`, `fast_kinetics_offset`, and `fast_kinetics_time_between_shots` IntParam/FloatParam blocks from `AndorCameraControl.build_fragment()` — all three now live in the config
- In `host_setup()` and `setup_fast_kinetics_mode()`: replace all `self.fast_kinetics_height.get()`, `self.fast_kinetics_offset.get()`, `self.fast_kinetics_time_between_shots.get()` → `self.andor_camera_config.fast_kinetics_height.get()` etc.
- Keep `add_pre_trigger_delay` as a constructor arg (not config-related)
- **Binding:** The mixin base classes currently call `self.andor_camera_control.bind_param("fast_kinetics_time_between_shots", self.delay_between_imaging_pulses)`. After this change, update those calls to `self.andor_camera_config.bind_param("fast_kinetics_time_between_shots", self.delay_between_imaging_pulses)`.

### Phase 3a — NormalisedFastKinetics config classes (`normalised_fast_kinetics_base.py`) — _parallel with 3b, 3c_

Create `NormalisedFKConfig(FastKineticsCameraConfig)`:

- Class attrs: `num_andor_images=4`, `num_images_per_series=2`, `num_grabber_rois=2`, `num_grabber_readouts=2`, `fast_kinetics_num_shots=2`, `fast_kinetics_height_default=constants.ANDOR_FAST_KINETICS_HEIGHT`, `fast_kinetics_offset_default=constants.ANDOR_FAST_KINETICS_OFFSET`
- `build_fragment(self, x0, y0, x1, y1, excited_shift=0)`: calls `super().build_fragment()` (creates FK params), then creates IntParams for the 4 ROI coordinates with the passed defaults. Pre-allocates `self.roi_buffer = [[np.int32(0)] * 4] * self.num_grabber_rois`
- `@portable get_rois()`: fills buffer by calling `self._calculate_rois(...)` using the IntParam values

Create `NormalisedFKDoubleTrapConfig(FastKineticsCameraConfig)` similarly, but `build_fragment` takes two sets of ROI coordinates (forward + backward) and `num_grabber_rois=4`. Its `get_rois()` returns both sets interleaved.

For `NormalisedFastKineticsBase`:

- Add `get_andor_camera_config_hook()`: calls `setattr_fragment("andor_camera_config", NormalisedFKConfig, x0=ANDOR_ROI_X0, ...)` with standard defaults; returns the result
- Remove `setup_andor_camera_control_hook()` override (fall back to `AndorImagingBase`'s implementation)
- Remove `get_grabber_roi_defaults()` FIXME method
- Update `bind_param` call to target `self.andor_camera_config`

For `NormalisedFastKineticsDoubleTrapBase`: same pattern with `NormalisedFKDoubleTrapConfig`.

### Phase 3b — TripleImage config classes (`triple_imaging_fast_kinetics_base.py`) — _parallel with 3a, 3c_

Create `TripleFKConfig(FastKineticsCameraConfig)`:

- Class attrs: `num_andor_images=3`, `num_images_per_series=3`, `num_grabber_rois=3`, `num_grabber_readouts=1`, `fast_kinetics_num_shots=3`, height/offset defaults from constants
- `build_fragment(self, x0, y0, x1, y1)`: calls `super().build_fragment()`, creates ROI IntParams, pre-allocates buffer
- `@portable get_rois()`: calls `self._calculate_rois(...)` (inherited from `FastKineticsCameraConfig`)

For `TripleImageFastKineticsBase`:

- Add `get_andor_camera_config_hook()` using `TripleFKConfig` with standard ROI defaults
- Remove `setup_andor_camera_control_hook()` and `get_grabber_roi_defaults()` FIXME
- Update `bind_param` call to target `self.andor_camera_config`

### Phase 3c — SingleImage config classes (`single_image_normalised_fast_kinetics_base.py`) — _parallel with 3a, 3b_

Create `SingleFKConfig(FastKineticsCameraConfig)` as a base for this family:

- Inherits FK params from `FastKineticsCameraConfig`
- Adds a **separate** static method `_calculate_rois_with_bg(height, offset, num_images, x0, y0, x1, y1, bg_width, excited_shift)` that produces signal + background ROIs (the existing `calculate_grabber_rois()` logic). Does **not** inherit `_calculate_rois` from `FastKineticsCameraConfig` — the formulas differ.

Create `SingleFKSingleTrapConfig(SingleFKConfig)`: `num_grabber_rois=6`, 2 images, 1 readout. `build_fragment(x0, y0, x1, y1, bg_width, excited_shift)` creates ROI + bg_width IntParams.

Create `SingleFKDoubleTrapConfig(SingleFKConfig)`: `num_grabber_rois=12`, 2 images, 1 readout. `build_fragment(fwd_x0/y0/x1/y1, bwd_x0/y0/x1/y1, bg_width, excited_shift)` creates 8 ROI IntParams + bg_width.

For `SingleImageNormalisedBase`:

- Replace `setup_andor_camera_control_hook()` with `get_andor_camera_config_hook()` (abstract)
- Remove abstract `get_grabber_roi_defaults()` FIXME
- Update `bind_param` call to `self.andor_camera_config`

For `SingleImageNormalisedSingleTrapBase`:

- Implement `get_andor_camera_config_hook()` using `SingleFKSingleTrapConfig` with standard ROI defaults
- Remove `get_grabber_roi_defaults()` FIXME
- Simplify `process_grabber_data_hook()` — see Phase 5

For `SingleImageNormalisedDoubleTrapBase`:

- Implement `get_andor_camera_config_hook()` using `SingleFKDoubleTrapConfig` with standard ROI defaults
- Remove `get_grabber_roi_defaults()` FIXME

### Phase 4 — Replace FIXME overrides in leaf classes — _depends on Phase 3a, 3b_

In `normalised_fast_kinetics.py`:

- `NormalisedDipoleTrapFastKineticsMixin`: replace `get_grabber_roi_defaults()` with `get_andor_camera_config_hook()` using `NormalisedFKConfig` subclassed or instantiated with dipole-trap ROI coords and `excited_shift=constants.ROI_SHIFT_EXCITED_STATE`. Remove `fast_kinetics_height_default`/`fast_kinetics_offset_default` class-attr overrides — pass `fast_kinetics_height_default` and `fast_kinetics_offset_default` as class attrs on an inline config subclass instead.
- `NormalisedXXODTFastKineticsMixin`: create `NormalisedXXODTFKConfig(NormalisedFKDoubleTrapConfig)` (or inline). Gravity correction logic stays as a build-time calculation inside `build_fragment()` of the config, computing corrected `excited_y0`/`excited_y1` defaults before passing them to the ROI IntParams.
- `NormalisedXXODTSpectroscopyFastKineticsMixin`: same pattern with the spectroscopy gravity timing.

In `triple_imaging_fast_kinetics.py`:

- `TripleImageDipoleTrapFastKineticsMixin`: override `get_andor_camera_config_hook()` using `TripleFKConfig` subclassed with dipole-trap constants and ROI coords.
- `TripleImageXXODTFastKineticsMixin`: subclass `TripleFKConfig` with `num_grabber_rois=6`, `build_fragment` taking both forward + backward ROI coords.

### Phase 5 — Simplify `process_grabber_data_hook` in SingleImage classes — _depends on Phase 3c_

The current `process_grabber_data_hook` in `SingleImageNormalisedSingleTrapBase` (and double-trap) accesses ROI areas via individual `self.andor_camera_control.roi_N_xN.get()` calls — one per coordinate per ROI. Replace with:

```python
rois = self.andor_camera_config.get_rois()
areas = [self.get_roi_area(rois[i]) for i in range(self.andor_camera_config.num_grabber_rois)]
```

This removes ~50 lines of repetitive code and works directly with the config's `get_rois()` output.

## Relevant files

- `repository/lib/fragments/cameras/andor_camera.py` — new `FastKineticsCameraConfig` (Phase 1), updated `AndorCameraControl` (Phase 2)
- `repository/lib/experiment_templates/mixins/andor_imaging/normalised_fast_kinetics_base.py` — Phase 3a; FIXMEs at lines 236, 521
- `repository/lib/experiment_templates/mixins/andor_imaging/normalised_fast_kinetics.py` — Phase 4; FIXMEs at lines 65, 132, 268
- `repository/lib/experiment_templates/mixins/andor_imaging/triple_imaging_fast_kinetics_base.py` — Phase 3b; FIXME at line 136
- `repository/lib/experiment_templates/mixins/andor_imaging/triple_imaging_fast_kinetics.py` — Phase 4; FIXMEs at lines 60, 99
- `repository/lib/experiment_templates/mixins/andor_imaging/single_image_normalised_fast_kinetics_base.py` — Phases 3c and 5; FIXMEs at lines 170, 331, 476

## Verification

Tests are slow — run targeted tests rather than the full suite at each step:

- After Phase 1+2: `pytest tests/test_compile_all.py -k "andor"` — verifies `AndorCameraControl` still constructs
- After each Phase 3 sub-step: `pytest tests/test_compile_all.py -k "<relevant experiment class>"` — verifies the affected experiment hierarchy compiles
- After Phase 5: `pytest tests/test_compile_all.py` — full compile check
- Final: `grep -r "get_grabber_roi_defaults\|roi_defaults=" repository/` returns no results

## Decisions

- `fast_kinetics_time_between_shots` moves into `FastKineticsCameraConfig` alongside `fast_kinetics_height` and `fast_kinetics_offset` — all FK configuration lives in the config, not the controller
- `calculate_grabber_rois()` module-level helper functions are replaced by static methods `_calculate_rois()` and `_calculate_rois_with_bg()` on the config base classes. The module-level functions can be kept temporarily as shims if needed during migration, then deleted.
- Inheritance for config classes: `FastKineticsCameraConfig` is the shared base for all FK configs. `SingleFKConfig` subclasses it for the background-ROI variant. `NormalisedFKConfig` and `TripleFKConfig` subclass `FastKineticsCameraConfig` directly. Keep the MRO flat — avoid deep chains.
- `_calculate_rois` and `_calculate_rois_with_bg` differ enough to live in separate classes rather than being parameterised variants of one function.
- The gravity correction logic in XXODT mixins remains as a build-time calculation (no behaviour change, same caveats about default parameter values).
- `num_andor_images`, `num_grabber_rois`, etc. move from mixin base classes to their config objects.
- `NormalisedXXODTFastKineticsMixin.host_setup()` warning checks reference `self.shelving_pulse_clearout_duration` etc. — these stay in the mixin unchanged (they check experiment params, not camera config params).
