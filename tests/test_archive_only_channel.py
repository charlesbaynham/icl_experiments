"""Tests for :class:`ArchiveOnlyOpaqueChannel`.

The channel must keep ndscan's normal archiving (data lands in the run HDF5)
while suppressing the broadcast of each scan point to the live dataset stream,
which is what bloats the master's dataset dict for large payloads like raw
camera frames.
"""

import numpy as np
from ndscan.experiment.result_channels import AppendingDatasetSink
from ndscan.experiment.result_channels import ArraySink
from ndscan.experiment.result_channels import OpaqueChannel

from repository.lib.result_channels import ArchiveOnlyOpaqueChannel


def _dataset_sink(device_mgr, dataset_mgr, argument_mgr, key):
    return AppendingDatasetSink((device_mgr, dataset_mgr, argument_mgr, {}), key)


def test_archive_only_channel_disables_broadcast_on_sink(
    device_mgr, dataset_mgr, argument_mgr
):
    sink = _dataset_sink(
        device_mgr, dataset_mgr, argument_mgr, "ndscan.rid_0.points.channel_img"
    )
    assert sink.broadcast is True  # ndscan's default
    ArchiveOnlyOpaqueChannel("img").set_sink(sink)
    assert sink.broadcast is False


def test_plain_opaque_channel_leaves_broadcast_enabled(
    device_mgr, dataset_mgr, argument_mgr
):
    sink = _dataset_sink(
        device_mgr, dataset_mgr, argument_mgr, "ndscan.rid_0.points.channel_img"
    )
    ArchiveOnlyOpaqueChannel("img")  # constructing one must not affect others
    OpaqueChannel("img").set_sink(sink)
    assert sink.broadcast is True


def test_set_sink_tolerates_non_dataset_sink():
    # Subscans attach an in-memory ArraySink, which has no broadcast flag.
    sink = ArraySink()
    ArchiveOnlyOpaqueChannel("img").set_sink(sink)  # must not raise
    sink.push(123)
    assert sink.get_all() == [123]


def test_archived_but_not_broadcast_end_to_end(
    device_mgr, dataset_mgr, dataset_db, argument_mgr
):
    key = "ndscan.rid_0.points.channel_img"
    sink = _dataset_sink(device_mgr, dataset_mgr, argument_mgr, key)
    ArchiveOnlyOpaqueChannel("img").set_sink(sink)

    sink.push(np.zeros((8, 8)))

    # Archived: present in the DatasetManager's local store, which write_hdf5
    # dumps into the run file.
    assert key in dataset_mgr.local
    # Not broadcast: it never reached the (mock) broadcast dataset DB.
    assert key not in dataset_db.data


def test_plain_channel_is_broadcast_end_to_end(
    device_mgr, dataset_mgr, dataset_db, argument_mgr
):
    key = "ndscan.rid_0.points.channel_scalar"
    sink = _dataset_sink(device_mgr, dataset_mgr, argument_mgr, key)
    OpaqueChannel("scalar").set_sink(sink)

    sink.push(1.0)

    assert key in dataset_db.data  # broadcast reached the DB
