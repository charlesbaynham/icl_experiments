# Handover: Fix `test_compile_all` failures from `add_grabber_config` branch

You are continuing a debugging session that was started on another machine. Read this entire document before doing anything.

## How to start

1. Invoke the `superpowers:systematic-debugging` skill (the previous session was using it).
2. You are on git branch `add_grabber_config`. The most recent commit you (a previous AI session) made on this branch is `6e0cc7ab` - "[AI] Fix non-FK imaging classes broken by AndorCameraConfig migration". The commit was already pushed to `origin/add_grabber_config`.
3. There are uncommitted local changes on this machine that you need to inspect, finish, then commit + push.

## The big picture

- The branch implements `.claude/plans/plan-migrateFkImagingToAndorCameraConfig.md` - a migration that moves `roi_*` and `fast_kinetics_*` parameters from `AndorCameraControl` to a new `AndorCameraConfig` object.
- The migration broke a bunch of tests in `tests/test_compile_all.py`.
- Your previous commit (`6e0cc7ab`) fixed the ones where `setattr_param_rebind` calls referenced params that no longer exist on `andor_camera_control`.
- After that, the user reported "I still see 13 failures. See e.g. SingleAndorImage."
- The remaining failures are caused by an _unrelated_ change in commit `50f4c87c` ("Ignore mixins"). That commit changed `tests/test_compile_all.py` from `not inspect.isabstract(obj)` to suffix-based filtering (skip classes whose name ends in `Base` or `Mixin`). Any abstract class that doesn't have a `Base` or `Mixin` suffix is now collected and fails when the test tries to instantiate it.
- The user wants the suffix-based filter kept (they wrote it). So the fix is to **rename the abstract classes to add `Mixin` (or `Base`) suffix, with a backwards-compat alias under the original name**.

## The pattern (already applied to several files)

For each abstract class `FooBar` that's subclassed from `ExpFragment` (directly or indirectly) and isn't suffix-marked, do:

```python
class FooBarMixin(...):  # was: class FooBar(...)
    ...
    # body unchanged

# At the bottom of the file:
FooBar = FooBarMixin
```

The alias preserves all existing imports of the form `from ... import FooBar`. The class's `__name__` is now `"FooBarMixin"`, so the suffix filter in `tests/test_compile_all.py` skips it.

Use `Base` suffix if the class name semantically reads as a base (e.g. `RedMOTWithExperiment` → `RedMOTWithExperimentBase`). Use `Mixin` for the others.

## What's already been done in this working tree (uncommitted)

Check `git status` first. As of handover, these files are modified with the rename-and-alias pattern applied:

- `repository/lib/experiment_templates/mixins/andor_imaging/single_andor_image.py` - `SingleAndorImage` → `SingleAndorImageMixin`
- `repository/lib/experiment_templates/mixins/andor_imaging/bg_corrected_andor_image.py` - `BGCorrectedAndorImage` → `BGCorrectedAndorImageMixin`, `BGCorrectedAndorImageSingleXODT` → `BGCorrectedAndorImageSingleXODTMixin`
- `repository/lib/experiment_templates/mixins/andor_imaging/em_gain.py` - `EMGain` → `EMGainMixin`
- `repository/lib/experiment_templates/mixins/andor_imaging/count_convert.py` - `CountConvertWithEMGain` → `CountConvertWithEMGainMixin` (also updated the `from ... import EMGain` to `EMGainMixin`)
- `repository/lib/experiment_templates/mixins/andor_imaging/midway_imaging.py` - `MidSequenceAndorImage` → `MidSequenceAndorImageMixin`
- `repository/lib/experiment_templates/mixins/andor_imaging/double_trap_imaging.py` - five classes renamed: `DoubleTrapImagingBasic`, `DoubleTrapImagingBGSubtracted`, `DoubleTrapImagingRepumpedNormalised`, `DoubleTrapImagingClockPulseNormalised`, `DoubleTrapImagingSpectroscopyRepumpedNormalised` (all `+Mixin`)
- `repository/lib/experiment_templates/red_mot_experiment.py` - `RedMOTWithExperiment` → `RedMOTWithExperimentBase`
- `repository/lib/experiment_templates/dipole_trap_experiment.py` - `DipoleTrapWithExperiment` → `DipoleTrapWithExperimentBase`
- `repository/lib/experiment_templates/mixins/painted_quadratic.py` - `MatterwaveLensingInBothDirection` → `MatterwaveLensingInBothDirectionMixin`
- `repository/lib/experiment_templates/mixins/red_spectroscopy.py` - `RedSpectroscopyDipoleTrap` → `RedSpectroscopyDipoleTrapMixin`
- `repository/lib/experiment_templates/mixins/trap_frequencies_mixin.py` - `SwitchHODT` → `SwitchHODTMixin`

There is also an untracked file `repository/lib/experiment_templates/mixins/andor_imaging/single_fast_kinetics.py` - that is **NOT** your work. Leave it alone (do not stage, do not delete).

## Verification step you were about to run when the handover happened

Verify the renames didn't break concrete subclasses:

```bash
pytest tests/test_compile_all.py -k "MeasureXXODTFrag or MeasureNarrowbandMOTFrag or MeasureNarrowbandMOTBGCorrectedFrag or BlastSingleDipole or MeasureSingleXODT" --no-header
```

You already verified that the renamed mixins themselves are now skipped by the collector:

```bash
pytest tests/test_compile_all.py -k "BGCorrectedAndorImage or DoubleTrapImaging or EMGain or MidSequenceAndorImage or SingleAndorImage or CountConvertWith or DipoleTrapWithExperiment or RedMOTWithExperiment or MatterwaveLensingInBothDirection or RedSpectroscopyDipoleTrap or SwitchHODT" --no-header --collect-only
# → "no tests collected (150 deselected)"
```

## What's left

1. Run the verification above. If anything fails, investigate. (When the handover happened the previous run was failing because of stray uncommitted changes in unrelated files - see "Pitfalls" below.)
2. There may be a few more abstract classes lurking that I haven't found. After the verification passes, scan for them:
    ```bash
    pytest tests/test_compile_all.py --collect-only --no-header 2>&1 | grep "Function test_build_all_fragments\[repository.lib"
    ```
    Anything that looks like an abstract base/mixin and doesn't end in `Base`/`Mixin` is a candidate. Run it individually to see if it fails with `Can't instantiate abstract class ... with abstract method`. If it does, apply the rename-and-alias pattern.
3. Commit (the user's instruction was: **no gpg, no pre-commit hooks** — i.e. `--no-verify --no-gpg-sign`). Commit message style on this branch uses the `[AI]` prefix; prior commits look like `[AI] Fix non-FK imaging classes broken by AndorCameraConfig migration`. Author/email comes from git config (Charles Baynham, c.baynham@imperial.ac.uk) — do **not** override.
4. `git push`.
5. **Then** run the full `pytest` (no args). The user explicitly said this takes >1h and to only do it once you're confident. Use `run_in_background: true` on the Bash call so you can do other things while it runs. Report results when done.

## Pitfalls (things that bit me)

- **Don't use `git stash` + `git checkout master -- .`**. I did this once to compare behavior with master, and it left merge-conflict markers in `repository/lib/fragments/cameras/andor_camera.py` and brought back unrelated stale staged/unstaged changes (someone's WIP DMA work in `dipole_trap_experiment.py`, `LMT_launch_mixins.py`, `tests/artiq_sample_dma_code.py`). If you need to compare with master, use `git show master:<path>` instead.
- If `git status` shows modifications to `dipole_trap_experiment.py`, `LMT_launch_mixins.py`, or `tests/artiq_sample_dma_code.py` and you didn't make them, run `git restore <file>` on each. They contain `core_dma` references that break `MeasureXXODTFrag` and other tests.
- **Do NOT run the full `pytest tests/test_compile_all.py` while iterating.** Each full run takes ~10-15 min. Run targeted `-k` selections instead. Only the final pre-push verification should be the full suite (and the user is OK with that one because it's the last one).
- The remaining pre-existing failure `MeasureXODTNewMolassesFrag` is unrelated to this work — it fails on master too (assertion in `pyaion/fragments/ramping_phase.py` about `general_setter_names` length). Don't try to fix it.

## Useful context

- The previous fix commit, `6e0cc7ab`, has its own commit message that summarises what was done in the previous step. `git show 6e0cc7ab` to read it.
- Plan being executed: `.claude/plans/plan-migrateFkImagingToAndorCameraConfig.md`. Worth skimming if you're unfamiliar with the migration shape.
- The test that filters classes is `tests/test_compile_all.py` lines ~31-49 (`get_all_of_class_from_module`).

## End-of-task report format

When you're done (after the full pytest finishes), tell the user:

- Which classes you renamed (one line each).
- The full pytest pass/fail count.
- Confirm the `MeasureXODTNewMolassesFrag` failure (if present) is the pre-existing unrelated one.
- The pushed commit hash.
