# Live-rig test plan: atom diagnostics (PR #28)

These diagnostics and the `default_scan` template build on machinery that has not
been validated end-to-end on the rig. Two `FIXME` markers (in
`repository/lib/experiment_templates/default_scan.py` and
`repository/diagnostics/diag_clock_polarization.py`) deliberately fail CI to block
merge to master until the live checks below are completed and the markers removed.

Do the checks in order; each later one assumes the earlier machinery works.

## 0. Prerequisites

- Atoms loading; XODT + clock stack known-good on the day.
- `oitg` importable in the runtime (the dataset-output analyses import it lazily).
- Confirm `DISABLE_EM_GAIN` interlock state allows the EM gain the diagnostics
  request (they only _read_ it; they never write it).

## 1. `default_scan` template (default-runnable scans)

Goal: confirm submitting a diagnostic with `arguments={}` actually runs the seeded
default scan (axes + repeats), and stays overridable.

1. Submit any diagnostic with `arguments={}`. Confirm in the dashboard that the
   scan axis, range, point count and repeat count match the `DefaultScanAxis`
   spec (not a single point at defaults).
2. Override the axis range/points from the dashboard; confirm the override wins.
3. Empty the scan in the dashboard; confirm it falls back to `no_axes_mode`
   without error.

If the seeded axes do **not** appear, the re-implemented `ArgumentInterface.build`
has drifted from the installed ndscan - reconcile it before proceeding, then
remove the FIXME in `default_scan.py`.

## 2. Dataset-output analyses (`dataset_fit_analysis.py`)

Goal: confirm the `CustomAnalysis` fits run at scan end and write values to
datasets (the whole point of the review: `OnlineFit` plots but does not output).

For `diag_background_field`, `diag_clock_rabi`, `diag_clock_line_centre`:

1. Run the default scan over a real line / flop.
2. Confirm the live `OnlineFit` curve still draws as before.
3. Confirm the new result channels are populated in the dataset:
    - background field: `line_centre_aom`, `line_fwhm` (+ `_err`)
    - clock Rabi: `pi_time`, `rabi_frequency` (+ `_err`)
    - clock line centre: `line_centre_aom`, `line_fwhm` (+ `_err`)
4. Sanity-check the dataset values against the on-screen `OnlineFit` annotation
   (they fit the same data with the same `oitg` procedure, so should agree).
5. If a fit-result key is wrong for the installed `oitg`, the analysis will raise
   a `KeyError` at scan end - fix the `fit_key` in the relevant `FitOutput`.

## 3. `diag_clock_line_centre` - delivery-AOM scan (review thread #3)

Goal: confirm the line is now scanned by the **SUServo delivery AOM frequency**
(`delivery_aom_frequency`), not by `extra_clock_detuning` on the OPLL.

1. Run the default scan; confirm a clean Lorentzian line vs AOM frequency.
2. Confirm the OPLL still does gravity compensation (line centre stable shot to
   shot; no drift that would indicate the OPLL is being mis-driven).
3. Tune the `_AOM_HALF_SPAN` / point count to span a few linewidths; fold the
   final good centre/range back into `repository/lib/constants.py`.

## 4. `diag_clock_polarization` - full rewrite (review thread #4)

This is the highest-risk change; the reviewer expects it to be broken on first
attempt. The corrected physics: the quantization field is rotated **in-trap**
(overriding the adiabatic Y->Z ramp endpoint), velocity selection is skipped, and
a single **pi/4** pulse addresses the whole thermal cloud.

1. **Field rotation is in-trap and persists.** Instrument / scope the comp-coil
   currents: confirm the bias field rotates to the scanned angle _while trapped_
   (during `dipole_trap_evaporation_hook_ramper`, after the nominal ramp) and that
   it is **not** reset between release and the clock pulse. If something downstream
   re-sets the bias field after release, move/repeat the rotation accordingly.
2. **Adiabaticity.** Vary `field_rotation_ramp_time` (and `_N_ROTATION_STEPS` if
   needed); confirm the excitation signal is insensitive to making the rotation
   slower (i.e. it is already adiabatic). If it depends on ramp time, increase the
   default until it plateaus.
3. **theta=0 reproduces nominal.** At `field_angle_deg=0` the field must equal the
   normal clock-spec operating field; confirm a normal clock excitation there.
4. **pi/4 on the thermal cloud.** Confirm the single pulse (no shelving) gives a
   sensible excitation on the unsliced cloud; adjust `pulse_area_fraction` if it
   saturates or is too weak.
5. **Modulation + axis.** Confirm excitation modulates with angle (period 180 deg)
   and that `polarization_axis_deg` / `polarization_contrast` land in the dataset
   and match the plotted modulation.
6. Only once 1-5 pass: remove the FIXME in `diag_clock_polarization.py`.

## 5. Compile check (cheap, do anytime)

Compile every changed Fragment via `test_compile_all` selectors (see the
`running-tests` skill) before/while iterating - catches kernel-compile errors in
the rewritten polarization hook and the line-centre AOM scan without needing
atoms.
