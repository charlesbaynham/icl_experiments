# Bug Hunt Report — 2026-05-31

Dynamic multi-angle audit of the active codebase (46 k lines, excluding `archived_experiments/`).

**Coverage:** 161 potential issues flagged → 18 confirmed real bugs after adversarial verification
**Breakdown:** 1 critical, 6 high, 5 medium, 6 low

---

## 🔴 Critical

### 1. `repository/lib/fragments/red_mot/red_beam_controller.py:312` — Wrong variable doubled for spinpol triangle wave

In `device_setup()`, after calculating `self.spinpol_ramp_rate`, the triangle-wave check incorrectly doubles `self.ramp_rate` (injection AOM) instead of `self.spinpol_ramp_rate` (spinpol AOM). Pure copy-paste error from the injection AOM block above. Result: spinpol AOM ramps at half the required speed, and the injection AOM rate gets spuriously doubled when spinpol uses triangle waves.

```python
if self.spinpol_ramp_type.get() == 0:
    # Triangle waves will need to ramp twice as quickly
    self.ramp_rate *= 2   # ← BUG: should be self.spinpol_ramp_rate
```

**Fix:** `self.spinpol_ramp_rate *= 2`

---

## 🟠 High

### 2. `repository/lib/fragments/fluorescence_pulse.py:308` — `do_clearout_pulse` ignores all parameters

The method accepts `ignore_initial_shutters`, `ignore_final_shutters`, and `duration` but calls `self.imaging_beam.do_clearout_pulse_base()` with no arguments. Callers in `LMT_launch_mixins.py` pass explicit durations (10 µs, 200 µs, etc.) and `ignore_final_shutters=True` — all silently discarded.

```python
@kernel
def do_clearout_pulse(self, ignore_initial_shutters=False, ignore_final_shutters=False, duration=-1.0):
    self.imaging_beam.do_clearout_pulse_base()  # ← args not forwarded
```

**Fix:** Pass the arguments through, as `do_imaging_pulse` already does.

### 3. `repository/lib/fragments/external_trigger.py:53` — `first_run` initialized to `False`, so `ttl.input()` never runs

The guard `if self.first_run:` in `device_setup()` is dead code because `first_run` starts as `False`. The TTL is never configured as an input.

```python
self.first_run = False   # ← BUG: should be True
```

**Fix:** `self.first_run = True`

### 4. `repository/lib/experiment_templates/mixins/evaporation_mixin.py:321` — Extra `self` passed to bound method

`self.DMA_initialization_hook_evap_with_field_ramp(self)` passes `self` explicitly to a bound method that only takes implicit `self`. This is a guaranteed `TypeError` at runtime when the DMA hook fires.

```python
self.DMA_initialization_hook_evap_with_field_ramp(self)  # ← remove (self)
```

### 5. `repository/lib/fragments/pulse_shaping.py:312` — Same spinpol ramp rate bug

Same copy-paste error: `self.ramp_rate *= 2` instead of `self.spinpol_ramp_rate *= 2`. Check whether one file imports from the other — this may be a duplicate or the same bug in two independent copies.

### 6. `repository/lib/fragments/set_eom_sidebands.py:56` — `index_of_stir_beam` check is unreachable

Initialized to `0`, so `is None` is always false. If the stir beam is absent, the code silently uses index 0 (wrong device) instead of raising `ValueError`.

```python
self.index_of_stir_beam = 0   # ← BUG: should be None
...
if self.index_of_stir_beam is None:   # ← dead code
    raise ValueError(...)
```

**Fix:** Initialize to `None`.

### 7. `repository/tests/test_DMA_return_values.py:44` — Test fetches `"dma2"` twice instead of `"dma1"`

Variable naming (`1a`, `1b`) indicates intent was to verify repeated `get_handle("dma1")` calls return the same handle. Instead `"dma2"` is fetched twice, `dma_handle_1b == dma_handle_2`, and the `"dma1"` handle is never played back.

```python
dma_handle_2 = self.core_dma.get_handle("dma2")
dma_handle_1b = self.core_dma.get_handle("dma2")  # ← should be "dma1"
```

---

## 🟡 Medium

### 8. `repository/lib/fragments/beams/reset_all_beams.py:158` — Urukul RF switches never turned off

`urukul_rf_switches` are collected in `host_setup()` but never added to `self.all_ttls`. `device_setup()` only iterates `all_ttls`, so Urukul RF switches are never reset. Comment on line 168 claims they are.

```python
self.all_ttls = suservo_shutter_ttls  # ← missing + urukul_shutter_ttls + urukul_rf_switches
```

### 9. `repository/lib/fragments/pulse_shaping.py:343` — RAM bounds check off by one

AD9910 RAM has 1024 words (addresses 0–1023). The check `offset + len(data) > 1023` incorrectly rejects valid writes ending exactly at address 1023. Should be `> 1024`.

```python
if offset + len(data) > 1023:   # ← should be > 1024
    raise ValueError("Data length + offset exceeds 1024 words")
```

---

## 🟢 Low

### 10. `repository/lib/fragments/beams/reset_all_beams.py:109` — `is []` identity check always false

`self.suservo_beam_infos is []` is always `False` in Python. The `NotImplementedError` is unreachable. (Line 104 already catches empty lists with `not`, so this is dead code.)

### 11. `repository/lib/experiment_templates/mixins/andor_imaging/single_image_normalised_fast_kinetics_base.py:373` — No-op expression

`self.fast_kinetics_offset` on a line by itself with no assignment — a refactoring leftover.

### 12. `repository/lib/fragments/dipole_trap/dipole_trap_phases.py:45` — Duplicate class attribute

`SUSERVO_UP_813` defined twice with identical values.

### 13–14. `repository/tests/test_painted_pulse.py:53` and `test_matterwave_collimation.py:33` — `logger.warning` format bug

`logger.warning("The pulse duration: ", value)` without `%s` placeholder. Logging fails internally (caught, so no crash, but value not logged).

### 15. `repository/tests/andor_fast_kinetics_usb.py:124` — Calls nonexistent method

`self.andor_camera_control.readout_image()` — method doesn't exist on `AndorCameraControl`. Would raise `AttributeError` immediately.

---

## Summary

| Category               | Count | Key theme                                              |
| ---------------------- | ----- | ------------------------------------------------------ |
| Copy-paste errors      | 3     | `ramp_rate` vs `spinpol_ramp_rate`, duplicate constant |
| Argument forwarding    | 2     | `do_clearout_pulse`, `DMA_initialization_hook`         |
| Unreachable/dead code  | 4     | `is None` checks, `is []`, no-op expressions           |
| Missing hardware state | 2     | RF switches not reset, TTL not configured as input     |
| Test bugs              | 3     | Wrong DMA handle, logging format, nonexistent method   |
| Off-by-one             | 1     | RAM bounds check                                       |
