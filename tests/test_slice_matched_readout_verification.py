"""Host verification for the slice-matched clock readout refactor.

Two guarantees:
 - the plain clock-spectroscopy experiments keep a byte-identical parameter
   schema (the source of the dashboard arginfo) after factoring the readout
   setpoint/duration into hooks (dump written for an out-of-band base/branch
   diff via ``SLICE_ARGINFO_OUT``),
 - the global clock-readout Frag gains a scannable ``readout_pulse_duration``
   whose default matches the slice, and at that default the slice-referenced
   setpoint law reproduces ``lmt_slice_setpoint`` exactly.
"""

import json
import os

from repository.LMT.lmt_interferometry import LMTInterferometrySymmetricFrag
from repository.LMT_declarative.lmt_declarative_global import (
    DeclarativeLMTGlobalSymmetricMachZehnderClockReadoutFrag,
)
from repository.lib import constants


def _collect_schema(frag):
    params: dict = {}
    schemata: dict = {}
    frag._collect_params(params, schemata, {})
    return {"params": params, "schemata": schemata}


def test_plain_clockspec_arginfo_dump(fragment_factory):
    frag = fragment_factory(LMTInterferometrySymmetricFrag)
    schema = _collect_schema(frag)

    out = os.environ.get("SLICE_ARGINFO_OUT", "/tmp/slice_plain_clockspec_arginfo.json")
    with open(out, "w") as fh:
        json.dump(schema, fh, indent=2, sort_keys=True, default=str)

    assert "readout_pulse_duration" not in json.dumps(schema)


def test_clock_readout_gains_scannable_duration(fragment_factory):
    frag = fragment_factory(DeclarativeLMTGlobalSymmetricMachZehnderClockReadoutFrag)
    schema = _collect_schema(frag)["schemata"]

    # ndscan serialises param defaults as string expressions in describe().
    readout_default = float(
        next(s["default"] for fqn, s in schema.items() if fqn.endswith("readout_pulse_duration"))
    )
    assert readout_default == constants.CLOCK_SHELVING_PULSE_TIME

    slice_dur = float(
        next(s["default"] for fqn, s in schema.items() if fqn.endswith("lmt_slice_duration"))
    )
    slice_setpoint = float(
        next(s["default"] for fqn, s in schema.items() if fqn.endswith("lmt_slice_setpoint"))
    )

    ratio = slice_dur / readout_default
    computed_setpoint = slice_setpoint * ratio * ratio
    assert computed_setpoint == slice_setpoint
