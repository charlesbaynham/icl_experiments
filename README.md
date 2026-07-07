# `stubs` branch

This is an **auto-generated, drastically simplified** mirror of the ICL ARTIQ
experiments repository. It exists so an ARTIQ master (or the dashboard's
experiment explorer) can enumerate every experiment **by name and description**
without needing any of the real dependencies - no `lib/` implementation code,
no Nix/Poetry packaging, no hardware drivers.

Every experiment that the ARTIQ explorer would discover on the source
branch(es) is represented here by a class that

- has the **same name** the explorer lists it under, and
- carries the **same docstring** (so the explorer shows the same description),

but whose body is the do-nothing
[`_Stub`](repository/stub_experiment.py) experiment (`run()` raises
`NotImplementedError`).

## Layout

```
repository/
  stub_experiment.py     # the only hand-written module: defines _Stub
  <mirrors the experiment file tree of the source branch(es)>
scripts/
  generate_stubs.py      # regenerates everything under repository/
```

The only file that is **not** regenerated is `repository/stub_experiment.py`
(it is rewritten verbatim from a template inside the generator). Everything
else under `repository/` is produced from scratch on every run.

Experiments that live under `repository/lib/...` on a source branch are
emitted with the `lib/` path segment stripped (e.g.
`repository/lib/calibrations/red_mot.py` -> `repository/calibrations/red_mot.py`)
so that this branch never contains a `lib/` folder. The generator aborts if
that stripping would ever collide with another file.

## Keeping in sync with master (and feature branches)

Regenerate whenever the source branches change:

```bash
# just track master
python scripts/generate_stubs.py --branches master

# union of several branches - the output is the union of every experiment
# found on any of them (earlier branches win docstring conflicts)
python scripts/generate_stubs.py --branches master feature/foo feature/bar
```

The script reads the source branches through `git` (it never checks them out)
and rewrites the working tree in place. Review the diff, then commit and push:

```bash
python scripts/generate_stubs.py --branches master
git add -A repository
git commit -m "Regenerate stubs from master"
git push
```

Run `python scripts/generate_stubs.py --branches master --dry-run` to see what
would change without touching the tree.

## What determines an "experiment"?

The generator statically reproduces ARTIQ's own discovery rules:

- `X = make_fragment_scan_exp(Frag)` -> an experiment named `X` with `Frag`'s
  docstring (ndscan experiments).
- A top-level class whose base chain reaches an experiment root
  (`EnvExperiment`/`Experiment`, `qbutler.Calibration`, `ndscan`'s
  `FragmentScanExperiment`, or `_Stub`) and whose name is not
  underscore-prefixed (raw ARTIQ experiments, monitors, ...).

Classes that are only *fragments* (`ExpFragment`/`Fragment`) are not
experiments until wrapped in `make_fragment_scan_exp`, and so are not stubbed
on their own.
