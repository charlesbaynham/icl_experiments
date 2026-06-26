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
attempt. **Corrected geometry (Charles, 2026-06-26):** the clock beam propagates
along **Z**, so its linear polarization lies in the **x-y plane**; the nominal
quantization field is along **x**. The field is therefore rotated **in the x-y
plane** (the old x-z rotation was wrong), at fixed **field magnitude** (per-axis
coil amps differ via `COIL_SENSITIVITY_{X,Y}_G_PER_A`), with Earth's-field
compensation applied by `constants.add_field_offset`. theta=0 reproduces the
nominal field.

Two variants ("trials") are provided:

- **`ClockPolarizationInTrapDiagnostic`** (Approach 1): in-trap adiabatic rotation,
  no velocity slice, single weak **pi/4** pulse on the whole thermal cloud
  immediately after release. Default scan `field_angle_deg` 0..360 deg.
- **`ClockPolarizationPostReleaseDiagnostic`** (Approach 2): normal in-trap ramp to
  the nominal x field, release, **normal velocity slice** (lower shelving
  setpoint), then rotate the field by the scanned angle (+/-90 deg) **post-release**
  and wait a scanned **`field_settle_time`** (eddy-current decay) before a
  **full-power spectroscopy pulse at the normal setpoint**. Default scan
  `field_angle_deg` -90..90 deg; also scan `field_settle_time`.

Live checks (do both variants; they cross-check each other):

1. **theta=0 reproduces nominal.** At `field_angle_deg=0` confirm a normal clock
   excitation (>90% excitation, >100k counts) - the field must equal the normal
   clock-spec operating field, with the applied z held at the pure Earth-comp value.
2. **Field rotation acts where intended.** Approach 1: scope the comp-coil currents
   to confirm the field rotates _in-trap_ (during `dipole_trap_evaporation_hook_ramper`,
   after the nominal ramp) and is **not** reset before the pulse. Approach 2: confirm
   the rotation happens _after_ the velocity slice and that `field_settle_time` is
   honoured before the pulse.
3. **Approach 1 adiabaticity.** Vary `field_rotation_ramp_time` (and
   `_N_ROTATION_STEPS` if needed); confirm the signal is insensitive to slower
   rotation. If it depends on ramp time, raise the default until it plateaus.
4. **Approach 2 eddy-current settle.** At a fixed angle (e.g. 90 deg) scan
   `field_settle_time`; confirm the excitation plateaus once eddy currents have
   decayed, and pick a default on the plateau.
5. **Pulse area.** Approach 1: confirm the pi/4 pulse on the unsliced cloud gives a
   sensible (unsaturated) excitation; tune `pulse_area_fraction`. Approach 2: the
   full pulse at the normal setpoint should behave like a normal velocity-sliced
   clock pulse at theta=0.
6. **Modulation + axis.** Confirm excitation modulates with angle (period 180 deg)
   and that `polarization_axis_deg` / `polarization_contrast` land in the dataset
   and match the plotted modulation. The two variants should agree on the axis.
7. **Gradient signs / handedness.** `COIL_SENSITIVITY_{X,Y,Z}_G_PER_A` signs are
   _assumed_ positive (labbook unclear). Confirm the rotation sense against a known
   direction (e.g. command a small +Y tilt and check the field/excitation moves the
   expected way) - a wrong Y sign mirrors the reported axis. Fix the constant sign
   if needed.
8. Only once 1-7 pass for at least one variant: remove the FIXME in
   `diag_clock_polarization.py`.

## 5. Compile check (cheap, do anytime)

Compile every changed Fragment via `test_compile_all` selectors (see the
`running-tests` skill) before/while iterating - catches kernel-compile errors in
the rewritten polarization hook and the line-centre AOM scan without needing
atoms.
