import logging

from artiq.coredevice.ad9910 import AD9910
from artiq.coredevice.core import Core
from artiq.language.core import kernel
from ndscan.experiment import ExpFragment
from ndscan.experiment import make_fragment_scan_exp
from numpy import int32
from numpy import int64

from dedrifter.dedrifter_cache_interface import DedrifterCacheAccess
from dedrifter.dedrifter_cache_interface import DedrifterCachedInfo
from repository.lib import constants
from repository.lib.fragments.timestamp_synchronizer import Timestamper

logger = logging.getLogger(__name__)


class UpdateDedrifters(ExpFragment):
    """
    Update parameters of the running dedrifters

    This experiment will update configuration stored in the core cache which
    will then be used by the idle kernel to control the dedrifters. This
    experiment must be run at least once, every time the ARTIQ crate is
    rebooted. It also required the idle_kernel to be the one defined in
    `idle_kernel_dedrifter.py`. Run::

        artiq_compile repository/idle_kernel_dedrifter.py
        artiq_coremgmt config write idle_kernel repository/idle_kernel_dedrifter.elf

    to update it if modified. This will persist through reboots.
    """

    def build_fragment(self):
        self.setattr_device("core")
        self.core: Core

        # Any DDS, to get access to the conversion functions
        self.dds: AD9910 = self.get_device("urukul0_ch0")

        self.infos: list[constants.DedrifterInfo] = constants.dedrifter_infos

        self.setattr_fragment("timestamper", Timestamper)
        self.timestamper: Timestamper

        self.cache_interface = DedrifterCacheAccess(self)

    def host_setup(self):
        self.cache_info = DedrifterCachedInfo(
            ramp_steps_wmu=[int64(0)] * len(self.infos),
            reference_times_mu=[int64(0)] * len(self.infos),
            reference_frequencies_mu=[int32(0)] * len(self.infos),
        )

        super().host_setup()

    @kernel
    def run_once(self):
        # Get the offset between the RTIO clock and UTC. We'll use this to
        # convert the reference times into RTIO units based on the current
        # device's sync.
        t_offset_mu = self.core.seconds_to_mu(self.timestamper.get_offset_from_utc())

        # Calculate the drift rate of the AD9910 FTWs in machine units. This
        # will be a tiny number, since machine units are ~ nanoseconds. We would
        # therefore be forced to work in floats, which are slow and inaccurate.
        #
        # To avoid this, we use that fact that the FTW is a 32-bit integer and
        # the core supports 64-bit arithmetic. We therefore make the convention
        # that all our arithmetic is performed with frequencies & drift rates
        # bitshifted left by 32 bits, to give us numerical precision but the
        # ability to calculate the next frequency set with a simple addition.
        #
        # Note that the only place we use "working machine units" (WMU) is in
        # the steps, not the absolute frequencies. Otherwise we'd overflow.
        num_steps_per_second = 1.0 / constants.T_STEP_DEDRIFTER
        for i in range(len(self.infos)):
            self.cache_info.ramp_steps_wmu[i] = int64(
                self.cache_interface.frequency_to_working_mu(
                    self.infos[i].ramp_rate / num_steps_per_second
                )
            )
            self.cache_info.reference_times_mu[i] = (
                self.core.seconds_to_mu(float(self.infos[i].reference_time))
                - t_offset_mu
            )
            self.cache_info.reference_frequencies_mu[i] = int32(
                self.dds.frequency_to_ftw(self.infos[i].reference_frequency)
            )

        # Write all these things into the cache
        print("Writing dedrifter cache info:")
        print("ramp_steps_wmu:", self.cache_info.ramp_steps_wmu)
        print("reference_times_mu:", self.cache_info.reference_times_mu)
        print("reference_frequencies_mu:", self.cache_info.reference_frequencies_mu)

        self.cache_interface.store_info(self.cache_info)


UpdateDedriftersExp = make_fragment_scan_exp(
    UpdateDedrifters, max_rtio_underflow_retries=0, max_transitory_error_retries=0
)
