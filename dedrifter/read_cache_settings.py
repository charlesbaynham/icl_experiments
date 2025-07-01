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

logger = logging.getLogger(__name__)


class ReadDedrifters(ExpFragment):
    """
    Read parameters of the running dedrifters
    """

    def build_fragment(self):
        self.setattr_device("core")
        self.core: Core

        # Any DDS, to get access to the conversion functions
        self.dds: AD9910 = self.get_device("urukul0_ch0")

        self.infos: list[constants.DedrifterInfo] = constants.dedrifter_infos

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
        self.cache_interface.get_info(self.cache_info)

        print("ramp_steps_wmu:", self.cache_info.ramp_steps_wmu)
        print("reference_times_mu:", self.cache_info.reference_times_mu)
        print("reference_frequencies_mu:", self.cache_info.reference_frequencies_mu)

        # Convert to SI units

        f_reference_frequencies_mu = [
            self.cache_info.reference_frequencies_mu[i] for i in range(len(self.infos))
        ]
        f_reference_frequencies = [
            self.dds.ftw_to_frequency(freq_mu) for freq_mu in f_reference_frequencies_mu
        ]

        print("reference_frequencies (Hz):", f_reference_frequencies)


ReadDedriftersExp = make_fragment_scan_exp(
    ReadDedrifters, max_rtio_underflow_retries=0, max_transitory_error_retries=0
)
