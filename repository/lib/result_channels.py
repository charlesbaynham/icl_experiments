"""ndscan result-channel helpers specific to this repository."""

from ndscan.experiment.result_channels import OpaqueChannel
from ndscan.experiment.result_channels import ResultSink


class ArchiveOnlyOpaqueChannel(OpaqueChannel):
    """:class:`OpaqueChannel` whose per-point scan data is written to the run's
    HDF5 archive but is *not* broadcast on the live dataset stream.

    ndscan mirrors every result channel's points into a broadcast dataset
    (``ndscan.rid_<rid>.points.channel_<name>``). For bulky payloads such as raw
    camera frames this inflates the ARTIQ master's live dataset dict; once the
    total exceeds sipyco's ~100 MB sync_struct init limit no client can
    (re)subscribe, which stalls the whole dataset stream (breaking the web UI's
    Plots view, dashboards and applets). ARTIQ still captures the full data in
    the run's HDF5 file (``archive`` defaults to ``True``), so nothing is lost
    for offline analysis, and opaque channels are never plotted live anyway.
    """

    def set_sink(self, sink: ResultSink) -> None:
        # ndscan builds the point sink with broadcast=True; the dataset-backed
        # sinks read this flag at push time, so flipping it makes the channel
        # archive-only. Non-dataset sinks (e.g. an in-memory ArraySink used by a
        # subscan) have no such flag and are left untouched.
        if hasattr(sink, "broadcast"):
            sink.broadcast = False
        super().set_sink(sink)
