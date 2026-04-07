import logging
import time

from artiq.coredevice.core import Core
from artiq.language import now_mu
from ndscan.experiment import FloatChannel
from ndscan.experiment import Fragment
from ndscan.experiment import IntParam
from ndscan.experiment import kernel
from ndscan.experiment import portable
from ndscan.experiment import rpc

logger = logging.getLogger(__name__)


@portable
def sum(list: list[float]) -> float:
    """
    Calculates the sum of a list of floats.
    Implemented here as @portable, since it's not included by default on the core.

    Args:
        list (list): List of floats.

    Returns:
        float: Sum of the floats in the list.
    """
    out = 0.0
    for num in list:
        out += num
    return out


@portable
def mean(list: list[float]) -> float:
    """
    Calculates the mean of a list of floats.
    Implemented here as @portable, since it's not included by default on the core.

    Args:
        list (list): List of floats.

    Returns:
        float: Mean of the floats in the list.
    """
    return sum(list) / len(list)


class Timestamper(Fragment):
    """
    Timestamper

    a) establish a link between the "machine units" timestamps running on the
    ARTIQ core, and real UTC time as known by the hosting PC

    b) if built with "record_timestamps=True", record timestamps for each point in an NDScan scan
    """

    def build_fragment(self, automatic_timestamp=False, record_timestamps=True):
        self.setattr_device("core")
        self.core: Core

        self.ntp_repeats = self.setattr_param(
            "ntp_repeats", IntParam, "Number of NTP repeats", default=10
        )

        if record_timestamps:
            self.timestamp_utc = self.setattr_result(
                "timestamp_utc",
                FloatChannel,
                display_hints={"priority": -1},
            )

        # Offset between ARTIQ seconds and UTC seconds. Calibrated using basic
        # version of the NTP protocol on the first shot
        self.artiq_utc_offset = float(0)

        self.automatic_timestamp = automatic_timestamp
        self.record_timestamps = record_timestamps
        self.kernel_invariants = getattr(self, "kernel_invariants", set())
        self.kernel_invariants.add("automatic_timestamp")
        self.kernel_invariants.add("record_timestamps")

        self._called_previous_point = True

    @kernel
    def device_setup(self):
        self.device_setup_subfragments()

        if self.record_timestamps and not self._called_previous_point:
            logger.error(
                "Timestamp's mark_timestamp() must be called exactly once per scan point. "
                "Use automatic_timestamp==True if you don't care about precise timing"
            )

        self._called_previous_point = False

        if self.artiq_utc_offset == 0:
            self._sync_timestamps()

        if self.automatic_timestamp:
            self.core.break_realtime()
            self.mark_timestamp()

    @kernel
    def _sync_timestamps(self):
        # Use a basic version of the NTP protocol to get the relationship
        # between UTC timestamps on the host PC and ARTIQ machine units. Note
        # that I'm assuming that the host PC and ARTIQ clocks are running at the
        # same rate - this is just a time synchronisation, not a frequency
        # calibration.

        # NTP uses four timestamps: t0, t1, t2, t3. Here's an ASCII diagram:
        #
        #   t0: client sends request \
        #        \
        #         \
        #          \
        #           | t1: server receives request
        #           |
        #           | t2: server sends response
        #          /
        #         /
        #        /
        #       /
        #   t3: client receives response
        #
        # t0 and t3 are in ARTIQ machine units, t1 and t2 are in UTC timestamps.
        # We don't have the ability to tell the difference between t1 and t2, so
        # we'll have to assume they're the same.

        offsets = [0.0] * self.ntp_repeats.get()
        for i in range(self.ntp_repeats.get()):
            t0_mu = self.core.get_rtio_counter_mu()
            t1 = self._get_utc_timestamp_from_host()
            t3_mu = self.core.get_rtio_counter_mu()
            t2 = t1

            t0 = self.core.mu_to_seconds(t0_mu)
            t3 = self.core.mu_to_seconds(t3_mu)

            offsets[i] = ((t1 - t0) + (t2 - t3)) / 2

        self.artiq_utc_offset = mean(offsets)

    @rpc
    def _get_utc_timestamp_from_host(self) -> float:
        """
        Get a UTC timestamp from the host via an RPC.
        """
        return time.time()

    @kernel
    def _get_utc_timestamp_from_mu(self) -> float:
        """
        Get a UTC timestamp from the current ARTIQ timestamp at the cursor's location

        This uses the offset calibrated in :meth:`~sync_timestamps`.
        """
        t_now_mu = now_mu()
        return self.core.mu_to_seconds(t_now_mu) + self.artiq_utc_offset

    @kernel
    def get_offset_from_utc(self) -> float:
        """
        Get the offset between the Sinara RTIO clock and UTC in seconds

        This is effectively the UNIX timestamp of the moment that the crate was
        turned on.
        """
        if not self.artiq_utc_offset:
            raise RuntimeError(
                "ARTIQ UTC offset has not been set - this Fragment has not been set up correctly."
            )

        return self.artiq_utc_offset

    @kernel
    def mark_timestamp(self):
        """
        Mark this moment on the ARTIQ timeline as the official timestamp of this
        NDScan point.

        This function must be called exactly once per scan point. If
        `automatic_timestamp` is true, this will happen automatically in
        :meth:`~device_setup`. For more precise timing, call this at an appropriate
        point in your sequence.
        """
        if self._called_previous_point:
            logger.error("mark_timestamp() was called more than once!")

        if not self.record_timestamps:
            raise RuntimeError(
                "mark_timestamp() was called, but this Fragment was built with record_timestamps=False"
            )

        self._called_previous_point = True
        self._push_timestamp(self._get_utc_timestamp_from_mu())

    @rpc(flags={"async"})
    def _push_timestamp(self, timestamp: float):
        self.timestamp_utc.push(timestamp)
