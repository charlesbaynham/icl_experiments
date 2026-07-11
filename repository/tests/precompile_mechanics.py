"""Empirically validate the two mechanics of a precompiled-kernel calibration loop.

A host-driven calibration architecture wants: the main experiment kernel
precompiled once; a mid-run calibration need signalled by raising an exception
from the kernel that unwinds to the host ``run()``; the host then runs
per-node precompiled calibration kernels and re-enters the precompiled main
kernel. Two mechanics need direct measurement on real hardware, hence two
experiments here.

Exp 1 (``EscapeReentryTiming``): a module-level custom exception raised inside a
precompiled kernel, caught on the host by class, followed by immediate
re-invocation of the same precompiled callable. Measures unwind latency and
re-entry deploy latency across repeated exceptional exits, and observes whether
a kernel attribute written before the raise is reflected on the host afterwards.

Exp 2 (``BackgroundCompileTiming``): precompiling the heavy kernel in a second
thread while the main thread is blocked inside a different precompiled kernel
that services synchronous RPCs. Measures the in-thread compile wall time against
the known 16.0 s solo baseline (RID 77433), the RPC-servicing jitter seen by the
host under GIL contention, and confirms the thread-compiled artifact deploys.

Custom-exception support (verified against the pinned legacy compiler):
- A user-defined ``Exception`` subclass raised in a kernel is embedded by object
  identity: ``artiq/compiler/embedding.py:514`` stores the host class via
  ``store_object(typ)`` and gives it a non-zero exception id.
- On the host, ``artiq/coredevice/comm_kernel.py:702`` reconstructs it with
  ``embedding_map.retrieve_object(core_exn.id)`` -- the *same* host class object
  -- so ``except CalibrationEscape`` catches it by class. (Builtin artiq
  exceptions take id 0 and the ``getattr(exceptions, name)`` path at :701.)
- Matches the tested pattern ``artiq/test/coredevice/test_rtio.py:33`` /
  ``test_portability.py:125`` (module-level ``class X(Exception)`` raised in a
  kernel, caught by class). So a custom class is used here, not a builtin.

Precompile-in-a-thread safety (verified):
- ``Core.precompile`` (``core.py`` precompile) calls ``compile`` then
  ``compile_and_upload_subkernels``. ``compile`` is device-free (Stitcher /
  Module / target only; touches no ``self.comm``).
- ``compile_and_upload_subkernels`` only touches ``self.comm`` (via
  ``upload_subkernel``) when ``embedding_map.subkernels()`` is non-empty. The
  heavy XODT kernel is single-core with no subkernels, so precompiling it
  touches no comm state.
- The concurrent main-thread run uses ``self.comm`` inside ``_run_compiled``
  (``load``/``run``/``serve``) and sets ``self.first_run``; the compiling thread
  reads only immutable config (``ref_period``, ``target_cls``, ``dmgr``). One
  shared ``Core`` object is therefore safe for compile-vs-run here; the native
  LLVM compile releases the GIL, letting the main thread's ``serve`` loop keep
  answering RPC pings. This safety holds only for a no-subkernel kernel.
"""

import json
import logging
import threading
import time

from artiq.coredevice.core import Core
from artiq.coredevice.exceptions import RTIOUnderflow
from artiq.experiment import delay
from artiq.experiment import kernel
from artiq.experiment import ms
from artiq.experiment import now_mu
from artiq.experiment import rpc
from artiq.experiment import s
from artiq.language import TBool
from ndscan.experiment import ExpFragment
from ndscan.experiment.entry_point import make_fragment_scan_exp
from ndscan.experiment.result_channels import LastValueSink

from repository.lib.calibrations.xodt_calibration import (
    _SimpleSingleXODTBGCorrectedFrag,
)

logger = logging.getLogger(__name__)

ESCAPE_RESULTS_DATASET = "precompile_mechanics.escape_results"
BGCOMPILE_RESULTS_DATASET = "precompile_mechanics.bgcompile_results"

SOLO_PRECOMPILE_HEAVY_S = 16.0  # RID 77433 solo core.precompile(heavy XODT)


class CalibrationEscape(Exception):
    """Raised inside the main kernel to unwind to the host for a calibration."""


class EscapeReentryFrag(ExpFragment):
    """Validate the custom-exception escape + fast precompiled re-entry loop."""

    N_CYCLES = 4

    def build_fragment(self):
        self.setattr_device("core")
        self.core: Core

        self.setattr_fragment("meas", _SimpleSingleXODTBGCorrectedFrag)
        self.meas: _SimpleSingleXODTBGCorrectedFrag
        self.detach_fragment(self.meas)

        self._measurement_sink = LastValueSink()
        self.meas.andor_sum_bg_corrected.set_sink(self._measurement_sink)

        self._entry_times: list = []
        self._raise_times: list = []
        self._return_marks: list = []
        self._escape = True
        self.probe_value = -1
        self._armed = False

    def _arm(self):
        if not self._armed:
            self.meas.host_setup()
            self._armed = True

    @rpc
    def _mark_entry(self):
        self._entry_times.append(time.monotonic())

    @rpc
    def _mark_raise(self):
        self._raise_times.append(time.monotonic())

    @rpc
    def _mark_return(self):
        self._return_marks.append(time.monotonic())

    @rpc
    def _should_escape(self) -> TBool:
        return self._escape

    @kernel
    def k_main(self):
        self._mark_entry()
        self.core.break_realtime()
        self.meas.device_setup()
        self.meas.run_once()
        self.meas.device_cleanup()
        self.probe_value = 42
        if self._should_escape():
            self._mark_raise()
            raise CalibrationEscape("mid-run calibration needed")
        self._mark_return()

    def run_once(self):
        self._arm()

        t0 = time.monotonic()
        main = self.core.precompile(self.k_main)
        precompile_s = time.monotonic() - t0

        cycles = []
        self._escape = True
        for i in range(self.N_CYCLES):
            self.probe_value = -1

            t_call = time.monotonic()
            caught_class = None
            right_class = False
            try:
                main()
            except CalibrationEscape as exc:
                t_catch = time.monotonic()
                caught_class = type(exc).__name__
                right_class = isinstance(exc, CalibrationEscape)
            else:
                t_catch = time.monotonic()
            t_raise = self._raise_times[-1] if self._raise_times else t_catch
            probe_after_catch = self.probe_value

            t_recall = time.monotonic()
            try:
                main()
            except CalibrationEscape:
                pass
            reentry_entry = self._entry_times[-1]

            cycles.append(
                {
                    "cycle": i,
                    "unwind_latency": t_catch - t_raise,
                    "reentry_deploy": reentry_entry - t_recall,
                    "caught_class": caught_class,
                    "right_class": right_class,
                    "probe_value_after_catch": probe_after_catch,
                }
            )

        self._escape = False
        t_norm0 = time.monotonic()
        normal_ok = False
        normal_error = None
        try:
            main()
            normal_ok = len(self._return_marks) > 0
        except Exception as exc:  # noqa: BLE001
            normal_error = repr(exc)
        normal_call_s = time.monotonic() - t_norm0

        results = {
            "custom_exception_supported": all(c["right_class"] for c in cycles),
            "exception_class": CalibrationEscape.__name__,
            "attribute_writeback_note": (
                "precompiled kernels compile with attribute_writeback=False "
                "(core.py precompile); host probe_value is expected to stay at "
                "its pre-call sentinel (-1) despite the kernel setting 42"
            ),
            "precompile_main_s": precompile_s,
            "normal_completion_after_escapes_ok": normal_ok,
            "normal_call_error": normal_error,
            "normal_call_s": normal_call_s,
            "cycles": cycles,
        }
        self.set_dataset(
            ESCAPE_RESULTS_DATASET,
            json.dumps(results),
            broadcast=True,
            persist=False,
            archive=True,
        )

        logger.info(
            "escape/reentry: precompile main=%.2fs | custom exc supported=%s | "
            "normal completion after escapes=%s",
            precompile_s,
            results["custom_exception_supported"],
            normal_ok,
        )
        logger.info(
            "  %-5s %14s %14s %10s %12s",
            "cyc",
            "unwind(ms)",
            "reentry(ms)",
            "class_ok",
            "probe",
        )
        for c in cycles:
            logger.info(
                "  %-5d %14.2f %14.1f %10s %12d",
                c["cycle"],
                1e3 * c["unwind_latency"],
                1e3 * c["reentry_deploy"],
                c["right_class"],
                c["probe_value_after_catch"],
            )


class BackgroundCompileFrag(ExpFragment):
    """Validate precompiling the heavy kernel in a thread while a kernel runs."""

    BUSY_ITERS = 45

    def build_fragment(self):
        self.setattr_device("core")
        self.core: Core

        self.setattr_fragment("meas", _SimpleSingleXODTBGCorrectedFrag)
        self.meas: _SimpleSingleXODTBGCorrectedFrag
        self.detach_fragment(self.meas)

        self._measurement_sink = LastValueSink()
        self.meas.andor_sum_bg_corrected.set_sink(self._measurement_sink)

        self._ping_times: list = []
        self._ping_slacks: list = []
        self._busy_entry_times: list = []
        self._busy_done_times: list = []
        self._heavy_entry_times: list = []
        self._heavy_done_times: list = []

        self._heavy_callable = None
        self._thread_t0 = 0.0
        self._thread_t1 = 0.0
        self._thread_error = None
        self._armed = False

    def _arm(self):
        if not self._armed:
            self.meas.host_setup()
            self._armed = True

    @rpc
    def _busy_entry(self):
        self._busy_entry_times.append(time.monotonic())

    @rpc
    def _busy_done(self):
        self._busy_done_times.append(time.monotonic())

    @rpc
    def _ping(self, i, slack):
        self._ping_times.append(time.monotonic())
        self._ping_slacks.append(int(slack))

    @rpc
    def _heavy_entry(self):
        self._heavy_entry_times.append(time.monotonic())

    @rpc
    def _heavy_done(self):
        self._heavy_done_times.append(time.monotonic())

    @kernel
    def k_busy(self):
        self._busy_entry()
        self.core.break_realtime()
        i = 0
        while i < self.BUSY_ITERS:
            delay(1 * s)
            slack = now_mu() - self.core.get_rtio_counter_mu()
            self.core.wait_until_mu(now_mu())
            self._ping(i, slack)
            i += 1
        self._busy_done()

    @kernel
    def k_heavy(self):
        self._heavy_entry()
        self.core.break_realtime()
        self.meas.device_setup()
        self.meas.run_once()
        self.meas.device_cleanup()
        self._heavy_done()

    def _compile_heavy_worker(self):
        self._thread_t0 = time.monotonic()
        try:
            self._heavy_callable = self.core.precompile(self.k_heavy)
        except Exception as exc:  # noqa: BLE001
            self._thread_error = repr(exc)
        finally:
            self._thread_t1 = time.monotonic()

    def run_once(self):
        self._arm()

        busy = self.core.precompile(self.k_busy)

        thread = threading.Thread(target=self._compile_heavy_worker)
        thread.start()
        time.sleep(1.0)

        t_busy0 = time.monotonic()
        underflow = False
        busy_error = None
        try:
            busy()
        except RTIOUnderflow:
            underflow = True
        except Exception as exc:  # noqa: BLE001
            busy_error = repr(exc)
        t_busy1 = time.monotonic()

        thread.join()
        t_join = time.monotonic()

        compile_wall_s = self._thread_t1 - self._thread_t0
        busy_wall_s = t_busy1 - t_busy0
        total_wall_s = t_join - self._thread_t0
        serial_sum_s = compile_wall_s + busy_wall_s

        intervals = [
            self._ping_times[k] - self._ping_times[k - 1]
            for k in range(1, len(self._ping_times))
        ]

        heavy_deploy = None
        heavy_error = None
        if self._heavy_callable is not None and self._thread_error is None:
            t_hcall = time.monotonic()
            try:
                self._heavy_callable()
                heavy_deploy = self._heavy_entry_times[-1] - t_hcall
            except Exception as exc:  # noqa: BLE001
                heavy_error = repr(exc)
        else:
            heavy_error = self._thread_error or "no heavy callable produced"

        def _stats(xs):
            if not xs:
                return {"n": 0}
            return {
                "n": len(xs),
                "min": min(xs),
                "max": max(xs),
                "mean": sum(xs) / len(xs),
            }

        results = {
            "solo_precompile_heavy_s_baseline": SOLO_PRECOMPILE_HEAVY_S,
            "in_thread_compile_wall_s": compile_wall_s,
            "thread_error": self._thread_error,
            "busy_wall_s": busy_wall_s,
            "busy_error": busy_error,
            "rtio_underflow": underflow,
            "n_pings": len(self._ping_times),
            "ping_interval_stats_s": _stats(intervals),
            "ping_intervals_s": intervals,
            "ping_slacks_mu": self._ping_slacks,
            "total_wall_concurrent_s": total_wall_s,
            "serial_sum_s": serial_sum_s,
            "overlap_saving_s": serial_sum_s - total_wall_s,
            "thread_compiled_heavy_deploy_s": heavy_deploy,
            "heavy_deploy_error": heavy_error,
        }
        self.set_dataset(
            BGCOMPILE_RESULTS_DATASET,
            json.dumps(results),
            broadcast=True,
            persist=False,
            archive=True,
        )

        logger.info(
            "bgcompile: in-thread compile=%.2fs (solo baseline %.1fs) | "
            "busy=%.2fs | underflow=%s | pings=%d",
            compile_wall_s,
            SOLO_PRECOMPILE_HEAVY_S,
            busy_wall_s,
            underflow,
            len(self._ping_times),
        )
        istats = results["ping_interval_stats_s"]
        if istats["n"]:
            logger.info(
                "  ping intervals (s): min=%.3f mean=%.3f max=%.3f (nominal 1.0)",
                istats["min"],
                istats["mean"],
                istats["max"],
            )
        logger.info(
            "  total concurrent=%.2fs vs serial sum=%.2fs (overlap saved %.2fs) | "
            "thread-compiled heavy deploy=%s",
            total_wall_s,
            serial_sum_s,
            results["overlap_saving_s"],
            (
                "%.3fs" % heavy_deploy
                if heavy_deploy is not None
                else "FAILED: %s" % heavy_error
            ),
        )


EscapeReentryTiming = make_fragment_scan_exp(EscapeReentryFrag)
BackgroundCompileTiming = make_fragment_scan_exp(BackgroundCompileFrag)
