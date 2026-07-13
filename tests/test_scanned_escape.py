"""Scanned-axes escape/resume (WP-B): a ``CalibrationEscape`` raised mid-scan
unwinds to the host, the DAG fix runs, and the scan RESUMES at the interrupted
point — every scan point lands exactly once.

The escape/re-enter loop lives in ndscan's ``ScanRunner.run`` (patched in
:mod:`qbutler.patch_ndscan`): on escape it runs ``fragment._recalibrate()`` and
loops back into ``acquire()``. Resume correctness is ndscan's own: a
``KernelScanRunner`` keeps the in-flight point in ``_current_chunk`` and only
pops it in ``_point_completed``, so an interrupted point is re-run and completed
points are not.

icl's test env has no kernel emulator (the mock core mock-runs kernels), so — as
in ``test_mixed_dag_calibration`` — only the on-core ``acquire`` body is emulated
on the host. Everything it drives (the patched ``ScanRunner.run`` loop, the real
``_get_param_values_chunk`` / ``_point_completed`` / ``_current_chunk``
bookkeeping, the ``ResultBatcher`` discard-on-interrupt, the axis/result sinks)
is production code.
"""

import gc

import pytest
from ndscan.experiment import ExpFragment
from ndscan.experiment.parameters import FloatParam
from ndscan.experiment.parameters import FloatParamHandle
from ndscan.experiment.result_channels import ArraySink
from ndscan.experiment.result_channels import FloatChannel
from ndscan.experiment.scan_generator import ListGenerator
from ndscan.experiment.scan_generator import ScanOptions
from ndscan.experiment.scan_runner import KernelScanRunner
from ndscan.experiment.scan_runner import ScanAxis
from ndscan.experiment.scan_runner import ScanSpec

from qbutler import dag
from qbutler.calibration import CalibrationError
from qbutler.calibration import CalibrationEscape


@pytest.fixture(autouse=True)
def _clear_dag():
    gc.collect()
    dag._dependency_map.clear()
    yield
    dag._dependency_map.clear()


class _ScanFrag(ExpFragment):
    """Scannable fragment that raises ``CalibrationEscape`` on a schedule.

    ``escape_schedule`` maps a scan-point value to ``(mode, count)``: escape the
    first ``count`` times that point runs, ``"before"`` or ``"after"`` pushing
    the result. ``_recalibrate`` (the fix hook the patched run loop calls) just
    counts calls; because each scheduled entry is consumed, the fix "settles"
    the drift and the re-run of that point completes.
    """

    max_recalibrations = 10

    def build_fragment(self):
        self.setattr_param("x", FloatParam, description="scan axis", default=0.0)
        self.x: FloatParamHandle
        self.setattr_result("y", FloatChannel)
        self.y: FloatChannel
        self.escape_schedule = {}
        self.fix_count = 0

    def run_once(self):
        v = self.x.get()
        mode, count = self.escape_schedule.get(v, ("none", 0))
        if count > 0:
            self.escape_schedule[v] = (mode, count - 1)
            if mode == "before":
                raise CalibrationEscape("drift before result push")
            if mode == "after":
                self.y.push(v)
                raise CalibrationEscape("drift after result push")
        self.y.push(v)

    def _recalibrate(self):
        self.fix_count += 1


class _EmulatedKernelScanRunner(KernelScanRunner):
    """A ``KernelScanRunner`` whose on-core ``acquire`` is emulated on the host.

    Faithfully mirrors the real ``acquire``/``_run_chunk``/``_run_point`` control
    flow (fetch a chunk, set params, run the point, mark complete) — but runs the
    point on the host so ``run_once`` (and its escapes) execute in-process. All
    the host bookkeeping it calls is the genuine ``KernelScanRunner`` code.
    """

    def acquire(self) -> bool:
        self._install_result_batcher()
        try:
            while True:
                chunk = self._get_param_values_chunk()
                if not chunk[0]:
                    return True
                for i in range(len(chunk[0])):
                    for axis_idx in range(len(self._axes)):
                        getattr(self, f"_param_setter_{axis_idx}")(chunk[axis_idx][i])
                    self._fragment.device_setup()
                    self._fragment.run_once()
                    self._point_completed()
        finally:
            self._remove_result_batcher()
            self._fragment.device_cleanup()


def _build_runner(device_mgr, dataset_mgr, argument_mgr):
    runner = _EmulatedKernelScanRunner((device_mgr, dataset_mgr, argument_mgr, {}))
    # ScanRunner.run closes the core each loop iteration; the test's mock
    # CommKernelDummy has no close() (a test-env teardown gap, not production
    # behaviour — the real comm closes fine), so make it a no-op here.
    runner.core.comm.close = lambda: None
    return runner


def _scan(
    fragment_factory,
    device_mgr,
    dataset_mgr,
    argument_mgr,
    escape_schedule,
    values,
    max_recalibrations=10,
):
    fragment = fragment_factory(_ScanFrag)
    fragment.escape_schedule = dict(escape_schedule)
    fragment.max_recalibrations = max_recalibrations

    param, store = fragment.override_param("x")
    axis = ScanAxis(param.describe(), "", store)
    spec = ScanSpec([axis], [ListGenerator(list(values), False)], ScanOptions(seed=0))

    result_sink = ArraySink()
    fragment.y.set_sink(result_sink)
    axis_sink = ArraySink()

    runner = _build_runner(device_mgr, dataset_mgr, argument_mgr)
    runner.run(fragment, spec, [axis_sink])

    return fragment, axis_sink.get_all(), result_sink.get_all()


class _PlainScanFrag(ExpFragment):
    """A vanilla scannable fragment with NO calibration hook (`_recalibrate`
    absent). Proves the global ScanRunner.run patch is inert for every ordinary
    ndscan scan: the escape branch is never taken and the loop is ndscan's."""

    def build_fragment(self):
        self.setattr_param("x", FloatParam, description="scan axis", default=0.0)
        self.x: FloatParamHandle
        self.setattr_result("y", FloatChannel)
        self.y: FloatChannel

    def run_once(self):
        self.y.push(self.x.get())


VALUES = [0.0, 1.0, 2.0, 3.0, 4.0, 5.0]


def test_non_calibrated_scan_unaffected_by_patch(
    fragment_factory, device_mgr, dataset_mgr, argument_mgr
):
    # No _recalibrate on the fragment -> the patched loop is byte-for-byte
    # ndscan's, so an ordinary scan runs to completion with every point once.
    fragment = fragment_factory(_PlainScanFrag)
    assert not hasattr(fragment, "_recalibrate")

    param, store = fragment.override_param("x")
    axis = ScanAxis(param.describe(), "", store)
    spec = ScanSpec([axis], [ListGenerator(list(VALUES), False)], ScanOptions(seed=0))
    result_sink = ArraySink()
    fragment.y.set_sink(result_sink)
    axis_sink = ArraySink()

    runner = _build_runner(device_mgr, dataset_mgr, argument_mgr)
    runner.run(fragment, spec, [axis_sink])

    assert axis_sink.get_all() == VALUES
    assert result_sink.get_all() == VALUES


def test_no_escape_all_points_once(
    fragment_factory, device_mgr, dataset_mgr, argument_mgr
):
    fragment, axis, results = _scan(
        fragment_factory, device_mgr, dataset_mgr, argument_mgr, {}, VALUES
    )
    assert axis == VALUES
    assert results == VALUES
    assert fragment.fix_count == 0


@pytest.mark.parametrize("k", [0.0, 3.0, 5.0])
def test_escape_before_push_lands_each_point_once(
    fragment_factory, device_mgr, dataset_mgr, argument_mgr, k
):
    # Escape at the first, a middle, and the last point (before pushing y).
    fragment, axis, results = _scan(
        fragment_factory,
        device_mgr,
        dataset_mgr,
        argument_mgr,
        {k: ("before", 1)},
        VALUES,
    )
    assert axis == VALUES, "every scan point recorded exactly once, in order"
    assert results == VALUES, "every result recorded exactly once, in order"
    assert fragment.fix_count == 1


@pytest.mark.parametrize("k", [0.0, 3.0, 5.0])
def test_escape_after_push_does_not_double_land(
    fragment_factory, device_mgr, dataset_mgr, argument_mgr, k
):
    # The interrupted point pushed a result BEFORE escaping; the ResultBatcher
    # must discard it so the re-run does not double-land it.
    fragment, axis, results = _scan(
        fragment_factory,
        device_mgr,
        dataset_mgr,
        argument_mgr,
        {k: ("after", 1)},
        VALUES,
    )
    assert axis == VALUES
    assert results == VALUES, "partial result discarded; point lands exactly once"
    assert fragment.fix_count == 1


def test_double_escape_same_point_resumes(
    fragment_factory, device_mgr, dataset_mgr, argument_mgr
):
    # Escape twice at the same point (an escape during the re-entered point):
    # recursion through the catch must settle, not hang or drop the point.
    fragment, axis, results = _scan(
        fragment_factory,
        device_mgr,
        dataset_mgr,
        argument_mgr,
        {2.0: ("before", 2)},
        VALUES,
    )
    assert axis == VALUES
    assert results == VALUES
    assert fragment.fix_count == 2


def test_escapes_at_several_points(
    fragment_factory, device_mgr, dataset_mgr, argument_mgr
):
    fragment, axis, results = _scan(
        fragment_factory,
        device_mgr,
        dataset_mgr,
        argument_mgr,
        {1.0: ("before", 1), 4.0: ("after", 1)},
        VALUES,
    )
    assert axis == VALUES
    assert results == VALUES
    assert fragment.fix_count == 2


def test_non_converging_calibration_raises_not_hangs(
    fragment_factory, device_mgr, dataset_mgr, argument_mgr
):
    # A point that always escapes must give up after max_recalibrations, not loop
    # forever.
    with pytest.raises(CalibrationError):
        _scan(
            fragment_factory,
            device_mgr,
            dataset_mgr,
            argument_mgr,
            {2.0: ("before", 999)},
            VALUES,
            max_recalibrations=3,
        )
