# AGENTS.md - Notes for AI Assistants

# ICL ARTIQ Experiments Repository

## Maintaining this file: prefer skills

This file is loaded into context on **every** agent run, so keep it lean -
only conventions that apply to most tasks belong here. Anything situational
(setup recipes, niche workflows, deep reference material) belongs in a Claude
Code skill under `.claude/skills/`, which agents load on demand; see
`nix-setup`, `running-tests` and `ndscan-artiq` for examples.

If a user asks you to "remember" something - even if they explicitly say to
add it to this file - and it would not be used in every run, suggest making a
skill instead and explain why: lean always-on context plus progressive
disclosure through skills gets noticeably better performance out of agents.

## Project Overview

This is the Imperial College London (ICL) ARTIQ experiments repository for controlling quantum physics experiments. ARTIQ (Advanced Real-Time Infrastructure for Quantum physics) is a leading-edge control system for quantum information experiments.

## Technology Stack

### Core Technologies

- **ARTIQ**: Quantum experiment control system with real-time capabilities
- **Python**: Version 3.10-3.11 (strict constraint)
- **Nix/NixOS**: Reproducible build environment and package management
- **Poetry**: Python dependency management (via poetry2nix)
- **ndscan**: Experiment scanning framework from Oxford Ion Trap Group

### Key Dependencies

- **PyAION**: AION Physics ARTIQ utilities and base functionality
- **sipyco**: Simple Python Communications library for ARTIQ
- **Wand**: Graphical experiment control interface
- **InfluxDB**: Time-series database for experiment data
- **Grafana**: Data visualization and monitoring

### Hardware Drivers

- Aravis (camera control via GigE Vision)
- Koheron CTL200 laser driver
- Toptica laser control
- Relocker board driver
- Andor cameras
- Various power supplies (Tenma, TTi)
- VXI-11 instruments

## Project Structure

```
repository/          # Main experiment code (importable as "repository")
├── lib/            # Shared library code and utilities
├── monitors/       # Database monitoring experiments
├── utilities/      # Helper experiments and tools
├── 689_spectroscopy/
├── blue_mot/
├── clock_interferometry/
├── clock_spectroscopy/
├── dipole_trap/
├── injected_diodes/
├── red_mot/
└── tests/

device_db_config/    # Hardware device definitions
├── devices.py      # Device configurations
├── _aliases.py     # Device aliases
└── configuration.py

dedrifter/          # Laser drift compensation system
tests/              # Unit tests (pytest)
docs/               # Sphinx documentation
scripts/            # Launch scripts and utilities
```

### Aravis Directory - DO NOT MODIFY

**The `nix/aravis/` directory contains third-party code that is NOT controlled by this repository.**

- Do NOT fix FIXMEs or TODOs in this directory
- Do NOT modify any files under `nix/aravis/`
- This is external/vendor code - any changes would be overwritten or lost

### Experiment structure

TODO: Describe how hooks and mixins are used with the main experiments.

## Development Guidelines

### Import Conventions

- Use **absolute imports** from the repository root: `from repository.lib import MyClass`
- This works because of our ARTIQ fork with PR #1805 merged
- Enables IDE autocomplete and better code navigation

### Code Style

- Use **Black** formatter (version 24.8.0)
- Run `pre-commit run --all` to format code
- Use `pre-commit install` for automatic formatting on commits
- All style rules are enforced by CI

### Comments and self-documenting code

- **Write self-documenting code; do not over-comment.** The people reading this
  are PhD-level physicists - do not explain standard physics (a Doppler shift, a
  π pulse, a light shift). Prefer a good name over a comment: a variable
  `doppler_shift_hz` needs no comment, and an expression that is obviously a
  Doppler shift needs at most `# Doppler shift` - usually nothing.
- **Comment only what is genuinely surprising**: a non-obvious mechanism, a
  convention we have invented, a sign or edge case that bites. Everything else
  should read straight from the code.
- Over-commenting bloats diffs and hides the code, and every comment is a second
  thing to keep in sync - a stale comment is a latent bug. A one-line bug is far
  easier to spot than one buried under fifty lines of explanation.

### ARTIQ-Specific Patterns

#### Experiment Classes

- Inherit from `artiq.experiment.EnvExperiment` or PyAION base classes
- Use `@kernel` decorator for real-time hardware control code
- Use `@rpc` for Python-side operations
- Be mindful of kernel/host boundary - only simple types cross it

#### Device Access

- Access hardware via `self.get_device()` in `build()` method
- Device definitions come from `device_db_config`
- Use descriptive device names and aliases

#### Clock Pulse Interactions

All interactions with the clock beam (OPLL, switch DDSes, and pulse firing) **must** go through the dedicated tracking wrapper methods. Never call the underlying hardware objects directly, as this will desynchronise the pulse recorder, timing state, and frequency tracking used by other parts of the experiment.

Use these methods instead of their raw counterparts:

| Task                      | Use this method                       | Never use                                            |
| ------------------------- | ------------------------------------- | ---------------------------------------------------- |
| Set OPLL frequency        | `set_clock_opll(freq)`                | `_clock_opll.clock_frequency_ramper.set(...)`        |
| Start OPLL ramp           | `start_clock_opll_ramp(...)`          | `_clock_opll.clock_frequency_ramper.start_ramp(...)` |
| Stop OPLL ramp            | `stop_clock_opll_ramp()`              | `_clock_opll.clock_frequency_ramper.stop_ramp()`     |
| Set up-beam DDS           | `set_clock_up_dds(freq, amp)`         | `clock_up_dds.set(...)` directly                     |
| Set down-beam DDS         | `set_clock_down_dds(freq, amp)`       | `clock_down_dds.set(...)` directly                   |
| Fire a spectroscopy pulse | `fire_lmt_pulse(freq, type, t_start)` | `clock_up_dds.sw.on/off` manually                    |

These methods update internal state (`_tracked_up_dds_freq`, `_tracked_down_dds_freq`, OPLL frequency records) that is read back by the pulse recorder and by gravity-compensation calculations (e.g. `get_t_start_shelving`). Bypassing them produces silently incorrect results.

The OPLL controller is owned by `ClockOPLLTrackingMixin` under the deliberately-internal name `_clock_opll`, so the tracked wrappers above are the path of least resistance; reaching through `self._clock_opll` to drive the ramper/DDS by hand is intentionally awkward and should not appear outside that mixin.

### Testing

- Write unit tests in `tests/` directory
- Or, add valid experiment Fragments into `repository/tests`. These must be runnable on the live system, but will also be compile by the unit tests
- Use `pytest` as the test runner
- Tests run in parallel (`-n 16` by default)
- Mark expected failures with `@pytest.mark.xfail`
- Test non-kernel utility functions (kernel testing is difficult)
- The `test_compile_all.py` test will compile every Fragment in the repo. It's very useful for catching errors, but also very expensive to run - it takes >1h. Only run the whole thing if explicitly requested, otherwise use pytest selectors to choose which tests from it you need.
- The **`running-tests`** skill has the exact local invocations (and the **`nix-setup`** skill covers installing Nix in an ephemeral container first).

### Documentation

- Use **Google-style docstrings** for Sphinx autodoc
- Docstrings should describe the current behaviour only; do not keep change history in them
- Documentation auto-generates from experiment files
- Build docs locally: `nix run .#docs`
- Documentation deploys to GitLab Pages on master branch
- Use UK English spelling throughout

### TODO/FIXME Convention

- Use `TODO` for planned improvements
- Use `FIXME` for temporary bodges that must be removed
- **FIXME markers will fail CI** - they are not allowed in committed code on the master branch

### Git branching conventions

- New features should usually be developed on feature branches
- All branches should have an associated merge request
- **The master branch should always be deployable** - no broken code or failing tests allowed

## Nix Environment

Used for all dependencies. Never make a python venv yourself.

Two Claude Code skills cover working with Nix locally - load them instead of
working it out from scratch:

- **`nix-setup`**: installing Nix in an ephemeral container (no systemd),
  including the aion-physics Cachix cache and manual daemon start.
- **`running-tests`**: running targeted tests via `nix run .#pytest`,
  including compiling individual Fragments and the pitfalls to avoid.

### Key Commands

- `nix develop` - Enter development shell with all dependencies
- `nix run .#full_stack` - Launch complete ARTIQ stack (master, controllers, DB, Grafana)
- `nix run .#dashboard` - Launch ARTIQ dashboard
- `nix run .#wand` - Launch Wand GUI
- `nix run .#update` - Update PyAION and ARTIQ versions

### Python Packages

#### Adding Dependencies

```bash
poetry add --lock package-name
nix develop -c true
```

This automatically updates both `pyproject.toml` and the Nix lock file. Do not
attempt to use poetry to build a python virtual environment - this is done with
Nix, but uses the poetry lock file.

#### Updating dependencies

```bash
poetry update --lock package-name
nix develop -c true
```

### System Packages

Edit `flake.nix` to add system dependencies or override package builds.

### Build Configuration

- Uses **poetry2nix** for Python package resolution
- First build can take ~30 minutes locally
- Use Cachix for pre-built binaries: `cachix use aion-physics`
- Binary cache populated by GitLab CI

## Special Considerations

### Network Configuration

- Server binds to `10.137.1.252` (ICL AION lab server IP)
- This allows multiple ARTIQ sessions on different IPs

### WSL Support

- Includes automatic DISPLAY environment variable setup for WSL
- X server detection via `scripts/wsl_display_fix.sh`

### Qt Applications

- Some drivers (relocker, pylablib, andor) need `dontWrapQtApps = true`
- Wand GUI needs special Qt wrapping in Nix

### ARTIQ Fork

- Uses custom ARTIQ fork with minimal changes from the m-labs upstream version

## Common Patterns

### Creating a basic Experiment

```python
from artiq.experiment import *

class MyExperiment(EnvExperiment):
    def build(self):
        self.setattr_device("core")
        # Get other devices here

    @kernel
    def run(self):
        self.core.reset()
        # Real-time code here
```

### Using ndscan

- Almost all experiments are generated from ndscan ExpFragments instead of raw ARTIQ EnvExperiments
- These should support ndscan parameters for scanning
- Parameters are added with self.setattr_param
- ResultChannels are added with self.setattr_result
- Every ResultChannel must be pushed to exactly once for every run of `run_once`, i.e. every point in an ndscan scan
- Allows complex multi-dimensional scans without code changes

#### Creating ndscan ExpFragments vs ARTIQ EnvExperiments

When creating an ndscan `ExpFragment`:

1. **Always use `build_fragment()` instead of `build()`** - ExpFragments use `build_fragment()`, not `build()`
2. **Always add `make_fragment_scan_exp` at the end of the file** - This creates the scannable experiment class:

    ```python
    from ndscan.experiment.entry_point import make_fragment_scan_exp, ExpFragment

    class MyExperimentFrag(ExpFragment):
        def build_fragment(self):
            # ... setup code ...

        def run_once(self):
            # ... experiment code ...

    # CRITICAL: Always add this line at the end!
    MyExperiment = make_fragment_scan_exp(MyExperimentFrag)
    ```

3. **Naming convention**: The `ExpFragment` class should be named `MyExperimentFrag`, and the scannable experiment class created by `make_fragment_scan_exp` should be named `MyExperiment` (i.e. without the "Frag" suffix).
4. **This is required** for the experiment to appear in the ARTIQ dashboard and be scannable

#### Converting ARTIQ arguments to ndscan parameters

When converting from ARTIQ `setattr_argument` to ndscan `setattr_param`:

```python
# OLD ARTIQ style
self.setattr_argument("frequency", NumberValue(default=100e6, unit="MHz"))

# NEW ndscan style
self.setattr_param(
    "frequency",
    FloatParam,
    description="DDS frequency",  # Add description
    default=100e6,  # In base SI units (Hz)
    unit="MHz",  # Display unit only
)
self.frequency: FloatParamHandle  # Add type annotation
```

Key differences:

- Use `FloatParam` instead of `NumberValue`
- Use `BoolParam` instead of `BooleanValue`
- Use `StringParam` instead of `EnumerationValue` (when appropriate)
- Always add a `description` parameter
- Always add type annotation with corresponding `*ParamHandle` type
- Parameter values must be accessed with `.get()` in `run_once()` and `prepare()`
- Device retrieval should typically move to `prepare()` method if it depends on parameter values

### Hardware Device Interaction

- Define devices in `device_db_config/`
- Access via `self.get_device("device_name")`
- Use type hints for IDE support

## Contributing

### Preference for PyAION

- Implement **common functionality in PyAION**, not locally
- Implement reusable code as ndscan Fragments
- This allows sharing improvements across institutions

### Use of Fragments

- Use ndscan Fragments for modular experiment components
- Where functionality is possible to implement with existing Fragment, do so
- Subfragments are added to fragments using ndscan's `setattr_fragment` function. This takes the _class_ of the fragment as its first argument, followed by any arguments required to construct the fragment which will be passed to the subfragment's `build_fragment` function. Note that it does not take an instance of the Fragment: it will construct the Fragment itself.

#### Common Fragment Mistakes

1. **NEVER instantiate Fragments yourself when using `setattr_fragment`**:

    ```python
    # INCORRECT - passing an instance
    self.setattr_fragment(
        "sigmaplus_setter",
        LibSetSUServoStatic(
            self,
            beam_info=constants.SUSERVOED_BEAMS["red_mot_sigmaplus"],
        ),
    )

    # CORRECT - passing the class and constructor arguments
    self.setattr_fragment(
        "sigmaplus_setter",
        LibSetSUServoStatic,
        channel=constants.SUSERVOED_BEAMS["red_mot_sigmaplus"].suservo_device,
    )
    ```

    - `setattr_fragment` expects the Fragment **class**, not an instance
    - Additional arguments are passed as keyword arguments to `setattr_fragment` itself
    - These arguments are forwarded to the Fragment's `build_fragment()` method
    - Never pass `self` to the Fragment constructor

2. **Use correct parameter names for factory functions**:

    ```python
    # INCORRECT - wrong parameter name
    self.setattr_fragment(
        "transparency_toggler",
        make_toggle_list_of_beams(
            beam_infos=[constants.SUSERVOED_BEAMS["blue_transparency_beam"]]
        ),
    )

    # CORRECT - correct parameter name
    self.setattr_fragment(
        "transparency_toggler",
        make_toggle_list_of_beams(
            suservo_beam_infos=[constants.SUSERVOED_BEAMS["blue_transparency_beam"]]
        ),
    )
    ```

    - Factory functions like `make_toggle_list_of_beams` return Fragment classes
    - Check the factory function signature for correct parameter names
    - `make_toggle_list_of_beams` uses `suservo_beam_infos=`, not `beam_infos=`
    - `make_set_beams_to_default` also uses `suservo_beam_infos=`

### Common imports overview

#### `pyaion.models.SUServoedBeam`

- Description of a beam, i.e. the AOM it requires, the AOM's frequency and amplitude, whether it has an assoviated shutter, etc.
- Often referred to as "beam info"

#### `repository.lib.constants.SUSERVOED_BEAMS`

- A dictionary of `SUServoedBeam` beam infos for all beams in the lab

#### `repository.lib.fragments.beams.toggling_beam_setter.ToggleListOfBeams`

- Turn a list of beams on/off quickly.
- Handle shutters, AOMs etc as defined in the beam's beam info definition.
- Often referred to as a "beam setter".
- Needs to be constructed using the factory function `repository.lib.fragments.beams.toggling_beam_setter.make_toggle_list_of_beams`.

#### `repository.lib.fragments.default_beam_setter.SetBeamsToDefaults`

- Set all beams to their default values (as defined in the beam info definition).
- Slow, but necessary for initial setup.
- Must be constructed with the factory function `pyaion.fragments.default_beam_setter.make_set_beams_to_default`.
- **Factory function parameters**:
    - `suservo_beam_infos`: List of SUServo beam infos to control
    - `urukul_beam_infos`: List of Urukul beam infos to control
    - `use_automatic_setup` (bool): If `True`, automatically calls `device_setup()` during the fragment's `device_setup()` phase. **Usually set to `True`**.
    - `use_automatic_turnon` (bool): If `True`, automatically turns on all beams with `turn_on_all(light_enabled=True)` during `device_setup()`. If `False`, you must manually call `turn_on_all(light_enabled=True)` in your code. **Application-dependent**: use `True` when you want beams on immediately, `False` when you need manual control (e.g., for quick toggling with `ToggleListOfBeams`).
- Example:
    ```python
    self.setattr_fragment(
        "beam_setter",
        make_set_beams_to_default(
            suservo_beam_infos=[constants.SUSERVOED_BEAMS["red_mot_diagonal"]],
            urukul_beam_infos=[],
            use_automatic_setup=True,
            use_automatic_turnon=True,  # Beams turn on automatically
        ),
    )
    ```

#### `pyaion.fragments.suservo.LibSetSUServoStatic`

- Used for low-level control of a SUServo device.
- Can set frequency, amplitude, setpoint, gains, and turn on/off the RF output.
- Commonly referred to as a "SUServo setter".

### Code Review

- All changes should pass CI (linting, tests, docs build)
- No FIXME markers allowed in commits on the master branch
- Document new experiments thoroughly

### Type annotation

- ARTIQ and ndscan make heavy use of `setattr_xxxxxx` methods. These follow the convention that `self.setattr_xxxxx("name", ObjectType)` will make an object of type `ObjectType` and save it as `self.name`.
- This confuses IDEs, so after every `setattr_xxx` call, use python type annotation to annotate the attribute that was just created.
- Example:

```python
from artiq.coredevice.core import Core

...

self.setattr_device("core")
self.core: Core
```

- One exception to this rule is ndscan parameters. These are called as e.g. `self.setattr_param("my_param", FloatParam, [...])` but create attrubtes of type `FloatParamHandle`, i.e. they make handles to the params. Example:

```python
self.setattr_param("my_param", FloatParam, description="My parameter", default=0.0)

self.my_param: FloatParamHandle  # CORRECT
self.my_param: FloatParam  # INCORRECT
```

- The "ccb" virtual device is hard to annotate. The correct way is like this:

```python
from artiq.master.worker_impl import CCB

...

    self.setattr_device("ccb")
    self.ccb: CCB
```

### Logging

- Use the python `logging` library, making a `logger = logging.getLogger(__name__)` in every module
- Use positional markers rather than f-string in logging calls. Example:

    ```python
    logger.info("The number is %f", number)  # CORRECT
    logger.info(f"The number is {number}")  # INCORRECT
    ```

### Units Convention

- All physical quantities are always in base SI units internally.

1. **Parameter Definitions (ndscan)**:

    ```python
    # CORRECT - default is in base SI units (Amperes), unit= is only for display
    self.setattr_param(
        "current",
        FloatParam,
        default=80.0e-3,  # 80 mA in Amperes (base SI unit)
        unit="mA"         # Display to user in milliamps
    )
    ```

    ```python
    # INCORRECT - default is already in mA, not in base SI
    self.setattr_param(
        "current",
        FloatParam,
        default=80.0,     # Wrong! This is 80 A, not 80 mA
        unit="mA"
    )
    ```

    ```python
    # INCORRECT - this is a unitless quantity so the "unit" keyword argument should not be provided
    self.setattr_param(
        "fraction_through_window",
        FloatParam,
        default=0.5,
        unit=""
    )
    ```

2. **Key Principles**:
    - The `default=` parameter is ALWAYS in base SI units (Hz, V, A, m, s, etc.)
    - The `unit=` parameter is ONLY for display/UI purposes
    - This ensures consistency: all code operates in base SI regardless of display units
    - Where appropriate, sensible "max" and "min" values should be added when making new parameters

3. **External Libraries**:
    - Where external libraries require non-base units (e.g. a laser library that takes current in "mA"), do the conversion as close as possible to the call to the external library
    - Example:
        ```python
        current = self.current_param.get()  # Get in Amperes (base SI)
        laser.set_current_ma(current_A * 1e3)    # Convert to mA for library
        ```

4. **Common Base SI Units**:
    - Frequency: Hz (not kHz, MHz, GHz)
    - Current: A (not mA, μA)
    - Voltage: V (not mV)
    - Time: s (not ms, μs, ns)
    - Length: m (not mm, μm, nm)
    - Power: W (not mW, μW)

5. **Variable names for physical quantities**
    - There is no need to specify the unit in the variable name, since it is always the base unit for that quantity
    - Example:

    ```python
    current = 15e-3  # CORRECT: current is 15mA
    logger.info("Current: %f mA", 1e3 * current)  # CORRECT: conversion is done for display only

    current_A = 1.0  # INCORRECT: we already know current is always in A, so no need to specify
    ```

#### ARTIQ units

- As a style choice, do not use the ARTIQ `ms`, `MHz` etc constants to multiply values. Just use normal floating point numbers
- Example:

```python
delay(10e-3)  # CORRECT: 10 ms in seconds (base SI unit)
delay(10 * ms)  # INCORRECT: do not use ms
```

## Best Practices

1. **Keep kernel code simple** - complex logic should be in host code
2. **Test extensively** - experiments control expensive equipment
3. **Document hardware configurations** - include calibration values in docstrings
4. **Use version control** - git hash is embedded in all datasets
5. **Monitor performance** - use monitors for long-term system health
6. **Backup regularly** - use provided backup scripts for datasets and database
7. **Update cautiously** - coordinate updates with other lab users
8. **Be cautious about break_realtime** - this will solve many RTIOUnderflow
   errors, but at the often unacceptable cost of losing real-time determinism

## Resources

- [PyAION Documentation](https://aion-physics.gitlab.io/code/artiq/pyaion/)
- [ARTIQ Manual](https://m-labs.hk/artiq/manual/)
- [ndscan GitHub](https://github.com/OxfordIonTrapGroup/ndscan)
- Local docs: `nix run .#docs`
