import logging
from dataclasses import dataclass

from artiq.coredevice.ad9910 import AD9910
from artiq.coredevice.cache import CoreCache
from artiq.coredevice.core import Core
from artiq.experiment import HasEnvironment
from artiq.language.core import kernel
from numpy import int32
from numpy import int64

logger = logging.getLogger(__name__)


# The number of bits to shift the FTW left by to get working machine units.
# This is a trade-off between precision and range. A larger value allows for
# smaller frequencies to be represented with higher precision, but reduces
# the maximum frequency that can be represented.
BITSHIFT = int64(63 - 23)


@dataclass
class DedrifterCachedInfo:
    ramp_steps_wmu: list[int64]
    reference_times_mu: list[int64]
    reference_frequencies_mu: list[int32]


class DedrifterCacheAccess(HasEnvironment):
    def build(self):
        self.setattr_device("core")
        self.core: Core
        self.setattr_device("core_cache")
        self.core_cache: CoreCache

        # Any DDS, to get access to the conversion functions
        self.dds: AD9910 = self.get_device("urukul0_ch0")

    @kernel(flags={"fast-math"})
    def frequency_to_working_mu(self, frequency: float) -> int64:
        """
        Convert a frequency in Hz to a working machine unit value.

        "Working machine units" (WMU) are a 64-bit integer representation of a
        frequency in machine-units of the DDS FTW but bit-shifted left by
        `BITSHIFT` bits. This allows us to perform arithmetic on the FTW without
        losing precision, since the FTW is a 32-bit integer.

        These must only be used for FTWs which are less than 2^`BITSHIFT` bits!
        Otherwise we'll overflow.
        """

        ftw_per_hz_64 = self.dds.ftw_per_hz * (int64(1) << BITSHIFT)
        ftw_64_float = ftw_per_hz_64 * frequency
        ftw_64 = int64(ftw_64_float)

        if abs(float(ftw_64) - ftw_64_float) > 1.0:
            logger.error(
                "Frequency %s is too high for the current BITSHIFT %s. "
                "Please increase BITSHIFT or reduce the frequency.",
                frequency,
                BITSHIFT,
            )
            raise ValueError("Frequency is too high for the current BITSHIFT.")

        return ftw_64

    @kernel(flags={"fast-math"})
    def working_mu_to_frequency(self, ftw_wmu: int64) -> float:
        """
        Convert a working machine unit value to a frequency in Hz.

        Note that this loses the precision of the working machine units. Do not
        use this number except for display purposes.
        """
        ftw_mu = int32((ftw_wmu >> BITSHIFT) & 0xFFFFFFFF)
        return self.dds.ftw_to_frequency(ftw_mu)

    @kernel(flags={"fast-math"})
    def working_mu_to_FTW(self, ftw_wmu: int64) -> int32:
        """
        Convert a working machine unit value to an FTW.

        Note that this loses the precision of the working machine units. Do not
        use this number except for display or output purposes.
        """
        return int32((ftw_wmu >> BITSHIFT) & 0xFFFFFFFF)

    @kernel
    def int64_to_32(self, input_array: list[int64], output_array: list[int32]):
        """
        Convert a list of int64 to a list of int32.

        The output list must be twice as long as the input list. The output list's elements will go:

        * LSB0
        * MSB0
        * LSB1
        * MSB1
        * etc.

        This is used to store the dedrifter information in the core cache, which
        can only store 32-bit integers.
        """

        if len(output_array) != 2 * len(input_array):
            raise ValueError("Output array must be twice as long as input array.")

        for i in range(len(input_array)):
            output_array[2 * i] = int32(input_array[i] & 0xFFFFFFFF)
            output_array[2 * i + 1] = int32((input_array[i] >> 32) & 0xFFFFFFFF)

    @kernel
    def int32_to_64(self, input_array: list[int32], output_array: list[int64]):
        """
        Convert a list of int32 to a list of int64.

        Undo the work of :meth:`~int64_to_32`.
        """
        if len(output_array) != len(input_array) // 2:
            raise ValueError("Output array must be half as long as input array.")

        for i in range(len(output_array)):
            output_array[i] = int64(
                (int64(input_array[2 * i]) & 0xFFFFFFFF)
                | ((int64(input_array[2 * i + 1]) & 0xFFFFFFFF) << 32)
            )

    @kernel
    def store_info(
        self, info  # type: DedrifterCachedInfo
    ):
        """
        Store information about the dedrifters to be run in the core cache.
        """

        # The core cache can only store 32-bit numbers, so we translate:

        translated_ramp_steps_wmu = [int32(0)] * (2 * len(info.ramp_steps_wmu))
        self.int64_to_32(
            input_array=info.ramp_steps_wmu, output_array=translated_ramp_steps_wmu
        )

        translated_reference_times_mu = [int32(0)] * (2 * len(info.reference_times_mu))
        self.int64_to_32(
            input_array=info.reference_times_mu,
            output_array=translated_reference_times_mu,
        )

        # Store the translated 64-bit arrays
        self.core_cache.put("translated_ramp_steps_wmu", translated_ramp_steps_wmu)
        self.core_cache.put(
            "translated_reference_times_mu", translated_reference_times_mu
        )

        # These are already 32-bit integers, so we can store them directly
        self.core_cache.put(
            "dedrifter_reference_frequencies", info.reference_frequencies_mu
        )

    @kernel
    def get_info(
        self, output  # type: DedrifterCachedInfo
    ):
        """
        Get information about the dedrifters from the core cache.
        """

        translated_ramp_steps_wmu = self.core_cache.get("translated_ramp_steps_wmu")
        translated_reference_times_mu = self.core_cache.get(
            "translated_reference_times_mu"
        )
        reference_frequencies_mu = self.core_cache.get(
            "dedrifter_reference_frequencies"
        )

        # If any of the cache entries are missing, raise an error
        if (
            len(translated_ramp_steps_wmu) == 0
            or len(translated_reference_times_mu) == 0
            or len(reference_frequencies_mu) == 0
        ):
            raise RuntimeError(
                "Dedrifter cache entries are missing. Please run the UpdateDedrifters experiment to update the cache."
            )

        # Convert the translated ramp steps and reference times back to int64
        ramp_steps_mu = [int64(0)] * (len(translated_ramp_steps_wmu) // 2)
        self.int32_to_64(
            input_array=translated_ramp_steps_wmu, output_array=ramp_steps_mu
        )
        reference_times_mu = [int64(0)] * (len(translated_reference_times_mu) // 2)
        self.int32_to_64(
            input_array=translated_reference_times_mu, output_array=reference_times_mu
        )

        # Check that all the lists are of the same length
        if not (
            len(ramp_steps_mu)
            == len(reference_frequencies_mu)
            == len(reference_times_mu)
        ):
            raise ValueError(
                "Dedrifter cache lists are not of the same length. Please rerun the UpdateDedrifters experiment to update the cache."
            )

        num_dedrifters = len(ramp_steps_mu)

        # Check that the output object's arrays are the same length as the cache
        if not (
            num_dedrifters
            == len(output.ramp_steps_wmu)
            == len(output.reference_frequencies_mu)
            == len(output.reference_times_mu)
        ):
            raise ValueError(
                "Dedrifter cache output arrays are not of the same length as the cache.",
            )

        # Copy the values from the cache to the output object. Note that this
        # must be an element-wise copy, otherwise the core cache will be mutable
        for i in range(num_dedrifters):
            output.ramp_steps_wmu[i] = ramp_steps_mu[i]
            output.reference_frequencies_mu[i] = reference_frequencies_mu[i]
            output.reference_times_mu[i] = reference_times_mu[i]
