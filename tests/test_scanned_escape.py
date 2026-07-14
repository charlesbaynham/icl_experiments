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
from types import SimpleNamespace

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

from qbutler import CalibratedExpFragment
from qbutler import dag
from qbutler.calibration import Calibration
from qbutler.calibration import CalibrationError
from qbutler.calibration import CalibrationEscape
from qbutler.calibration import CalibrationResult
from qbutler.client import exclude_calibration_channels_from_scan


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


# --------------------------------------------------------------------------- #
# Scan with a REAL attached Calibration node (live finding, RID 77567):
# the node's status/data channels are pushed by the check/fix walk, not per
# scan point, so if the scan sinks them the per-point ResultBatcher fails the
# whole scan. The client must strip their sinks in the scanned path.
# --------------------------------------------------------------------------- #


class _ScanCal(Calibration):
    """Host parabola check, optimum 2.0, broken at its default 5.0."""

    def build_calibration(self):
        self.set_timeout(300.0)
        self.setattr_param_optimizable(
            "cal_param", "Cal param", min=0.0, max=10.0, default=5.0
        )
        self.cal_param: FloatParamHandle

    def check_own_state(self):
        data = 10.0 - abs(self.cal_param.get() - 2.0)
        result = CalibrationResult.OK if data > 9.5 else CalibrationResult.BAD_DATA
        return result, data


class _CalibratedScanFrag(CalibratedExpFragment):
    """The scanned-demo shape: a calibrated fragment with a scan axis whose
    run_once escapes while the DAG is drifted (host mirror of the @kernel
    recalibrate_if_needed) and pushes one science result per point."""

    def build_fragment(self):
        self.setattr_device("core")
        self.setattr_param("x", FloatParam, description="scan axis", default=0.0)
        self.x: FloatParamHandle
        self.setattr_result("y", FloatChannel)
        self.y: FloatChannel
        self.setattr_calibration(_ScanCal)
        self._ScanCal: _ScanCal

    def run_once(self):
        if self._needs_recalibration():
            raise CalibrationEscape("a calibration dependency needs recalibrating")
        self.y.push(self.x.get())


def _sink_all_channels(fragment):
    """Mirror TopLevelRunner.build: give every save-by-default channel in the
    tree a sink, and return (tlr_stand_in, science_sink, cal_channels)."""
    chan_dict = {}
    fragment._collect_result_channels(chan_dict)
    scan_result_sinks = {}
    short_names = {}
    science_sink = None
    for path, channel in chan_dict.items():
        if not channel.save_by_default:
            continue
        sink = ArraySink()
        channel.set_sink(sink)
        scan_result_sinks[channel] = sink
        short_names[channel] = path.replace("/", "_")
        if path.endswith("y"):
            science_sink = sink
    tlr = SimpleNamespace(
        _scan_result_sinks=scan_result_sinks,
        _short_child_channel_names=short_names,
    )
    return tlr, science_sink


def _run_calibrated_scan(
    fragment_factory, device_mgr, dataset_mgr, argument_mgr, apply_fix
):
    fragment = fragment_factory(_CalibratedScanFrag)
    tlr, science_sink = _sink_all_channels(fragment)
    if apply_fix:
        exclude_calibration_channels_from_scan(fragment, tlr)

    param, store = fragment.override_param("x")
    axis = ScanAxis(param.describe(), "", store)
    spec = ScanSpec([axis], [ListGenerator(list(VALUES), False)], ScanOptions(seed=0))
    axis_sink = ArraySink()

    runner = _build_runner(device_mgr, dataset_mgr, argument_mgr)
    runner.run(fragment, spec, [axis_sink])
    return fragment, tlr, axis_sink.get_all(), science_sink.get_all()


def test_sinked_calibration_channels_fail_the_scan_rid77567(
    fragment_factory, device_mgr, dataset_mgr, argument_mgr
):
    # Regression reproduction of the live failure: without the sink strip, the
    # first completed point trips the ResultBatcher on the cal's status channel.
    with pytest.raises(ValueError, match="status"):
        _run_calibrated_scan(
            fragment_factory, device_mgr, dataset_mgr, argument_mgr, apply_fix=False
        )


def test_calibrated_scan_with_escape_lands_all_points_once(
    fragment_factory, device_mgr, dataset_mgr, argument_mgr
):
    # With calibration channels excluded, the demo shape works end-to-end: the
    # drifted DAG escapes at point 0, the REAL inherited _recalibrate
    # (fix_targets walk) fixes the node, and the scan resumes to completion.
    fragment, tlr, axis, results = _run_calibrated_scan(
        fragment_factory, device_mgr, dataset_mgr, argument_mgr, apply_fix=True
    )
    assert axis == VALUES
    assert results == VALUES
    assert fragment._ScanCal.cal_param.get() == pytest.approx(2.0), (
        "the real fix walk ran and committed the optimum"
    )
    # The cal channels are fully out of the scan: unsinked and unadvertised.
    for channel, name in list(tlr._short_child_channel_names.items()):
        assert "_ScanCal" not in name
    assert all(
        channel.sink is None
        for path, channel in _collect_all_channels(fragment).items()
        if "_ScanCal" in path
    )


def _collect_all_channels(fragment):
    chan_dict = {}
    fragment._collect_result_channels(chan_dict)
    return chan_dict
