"""Measure the host->core deploy latency of a PRECOMPILED heavy kernel.

Motivating question: a host-driven calibration DAG wants to call one
precompiled kernel per node. Compilation is ~60 s, so compile-per-entry is a
non-starter; the architecture only works if, *once precompiled*, a single
invocation's upload+launch latency is sub-second (execution time is then just
the real work). This experiment times both fractions directly against the real
heavy XODT imaging measurement, run dark (no atoms needed).

The kernel's first statement is an RPC (`_mark_entry`) whose host arrival
timestamps when the core actually begins executing: everything between t_call
(host, pre-invocation) and that arrival is upload+launch, i.e. deploy latency.
Note the entry RPC is synchronous, so its round trip lands inside the following
execution window (t_done - t_entry), not in the deploy latency; the reported
execution figure is therefore a slight over-estimate and deploy latency a clean
lower-bound-free measurement of "get the binary onto the core and running".
"""

import json
import logging
import time

from artiq.coredevice.core import Core
from artiq.experiment import delay
from artiq.experiment import kernel
from artiq.experiment import ms
from artiq.experiment import rpc
from ndscan.experiment import ExpFragment
from ndscan.experiment.entry_point import make_fragment_scan_exp
from ndscan.experiment.result_channels import LastValueSink

from repository.lib.calibrations.xodt_calibration import (
    _SimpleSingleXODTBGCorrectedFrag,
)

logger = logging.getLogger(__name__)

RESULTS_DATASET = "precompile_timing.results"


class PrecompileTimingFrag(ExpFragment):
    """Time deploy latency + execution of a precompiled heavy imaging kernel."""

    def build_fragment(self):
        self.setattr_device("core")
        self.core: Core

        self.setattr_fragment("meas", _SimpleSingleXODTBGCorrectedFrag)
        self.meas: _SimpleSingleXODTBGCorrectedFrag
        # Detach so the heavy measurement owns its own lifecycle/channels and
        # does not impose required scan arguments on this top-level experiment
        # (mirrors SingleXODTCalibration).
        self.detach_fragment(self.meas)

        self._measurement_sink = LastValueSink()
        self.meas.andor_sum_bg_corrected.set_sink(self._measurement_sink)

        self._entry_times: list = []
        self._done_times: list = []
        self._armed = False

    def _arm(self):
        if not self._armed:
            self.meas.host_setup()
            self._armed = True

    @rpc
    def _mark_entry(self):
        self._entry_times.append(time.monotonic())

    @rpc
    def _mark_done(self):
        self._done_times.append(time.monotonic())

    @kernel
    def k_heavy(self):
        self._mark_entry()
        self.core.break_realtime()
        self.meas.device_setup()
        self.meas.run_once()
        self.meas.device_cleanup()
        self._mark_done()

    @kernel
    def k_light(self):
        self._mark_entry()
        self.core.break_realtime()
        delay(1 * ms)
        self._mark_done()

    def _invoke(self, kind, callable_):
        t_call = time.monotonic()
        callable_()
        t_return = time.monotonic()
        t_entry = self._entry_times[-1]
        t_done = self._done_times[-1]
        return {
            "kind": kind,
            "t_call": t_call,
            "t_entry": t_entry,
            "t_done": t_done,
            "t_return": t_return,
            "deploy_latency": t_entry - t_call,
            "execution": t_done - t_entry,
            "roundtrip": t_return - t_call,
        }

    def run_once(self):
        self._arm()

        t0 = time.monotonic()
        heavy = self.core.precompile(self.k_heavy)
        t1 = time.monotonic()
        light = self.core.precompile(self.k_light)
        t2 = time.monotonic()
        precompile_heavy_s = t1 - t0
        precompile_light_s = t2 - t1

        records = []
        # Three heavy calls, then heavy/light alternation: switching binaries
        # each call defeats any same-binary comm caching, matching DAG node
        # switching.
        sequence = [
            "heavy",
            "heavy",
            "heavy",
            "heavy",
            "light",
            "heavy",
            "light",
            "heavy",
            "light",
        ]
        callables = {"heavy": heavy, "light": light}
        for kind in sequence:
            records.append(self._invoke(kind, callables[kind]))

        # One plain (non-precompiled) heavy call: compile+upload+run end to end.
        # This is the ~60 s baseline that exposes the compile fraction directly.
        t_base0 = time.monotonic()
        self.k_heavy()
        baseline_s = time.monotonic() - t_base0

        results = {
            "artiq_precompile_reuploads_binary_each_call": True,
            "caveat": (
                "entry RPC is synchronous; its round trip is counted in "
                "execution (t_done - t_entry), not in deploy_latency"
            ),
            "precompile_heavy_s": precompile_heavy_s,
            "precompile_light_s": precompile_light_s,
            "baseline_plain_heavy_call_s": baseline_s,
            "records": records,
        }
        self.set_dataset(
            RESULTS_DATASET,
            json.dumps(results),
            broadcast=True,
            persist=False,
            archive=True,
        )

        logger.info(
            "precompile: heavy=%.2fs light=%.2fs | baseline plain heavy=%.2fs",
            precompile_heavy_s,
            precompile_light_s,
            baseline_s,
        )
        logger.info("  %-6s %12s %12s %12s", "kind", "deploy(ms)", "exec(ms)", "rt(ms)")
        for r in records:
            logger.info(
                "  %-6s %12.1f %12.1f %12.1f",
                r["kind"],
                1e3 * r["deploy_latency"],
                1e3 * r["execution"],
                1e3 * r["roundtrip"],
            )


PrecompileTiming = make_fragment_scan_exp(PrecompileTimingFrag)
