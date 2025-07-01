from artiq.coredevice.ad9910 import AD9910
from artiq.coredevice.core import Core
from artiq.coredevice.ttl import TTLOut
from artiq.experiment import EnvExperiment
from artiq.language import delay
from artiq.language import delay_mu
from artiq.language import now_mu
from artiq.language.core import kernel
from numpy import int32
from numpy import int64

from dedrifter.dedrifter_cache_interface import DedrifterCacheAccess
from dedrifter.dedrifter_cache_interface import DedrifterCachedInfo
from repository.lib import constants


class IdleKernel(EnvExperiment):
    """
    Idle kernel to dedrift the cavity
    """

    def build(self):
        self.kernel_invariants = getattr(self, "kernel_invariants", set())

        self.setattr_device("core")
        self.core: Core

        self.infos: list[constants.DedrifterInfo] = constants.dedrifter_infos
        self.kernel_invariants.add("infos")

        self.led: TTLOut = self.get_device("led1")
        self.kernel_invariants.add("led")

        self.cache_interface = DedrifterCacheAccess(self)
        self.kernel_invariants.add("cache_interface")

        self.ad9910s: list[AD9910] = [
            self.get_device(info.channel_name) for info in self.infos
        ]
        self.kernel_invariants.add("ad9910s")

        # Declare kernel variables - not invariant
        self.cache_info = DedrifterCachedInfo(
            ramp_steps_wmu=[int64(0)] * len(self.infos),
            reference_times_mu=[int64(0)] * len(self.infos),
            reference_frequencies_mu=[int32(0)] * len(self.infos),
        )

    @kernel
    def run(self):
        core_log("Idle dedrifter started")

        # Retrieve the dedrifter information from the cache
        try:
            self.cache_interface.get_info(self.cache_info)
        except RuntimeError:
            core_log(
                "Error retrieving dedrifter information from cache. Please run the UpdateDedrifters experiment."
            )

            while True:
                pass  # Wait forever. This kernel will be interrupted if a new experiment is run

        core_log("ramp_steps_wmu:", self.cache_info.ramp_steps_wmu)
        core_log("reference_times_mu:", self.cache_info.reference_times_mu)
        core_log("reference_frequencies_mu:", self.cache_info.reference_frequencies_mu)

        # Assume the AD9910s are already initiated - the startup kernel should
        # do this

        t_step_mu = self.core.seconds_to_mu(constants.T_STEP_DEDRIFTER)

        # Add loads of slack
        self.core.reset()
        delay(1.0)

        f_reference_frequencies_mu = [
            self.cache_info.reference_frequencies_mu[i] for i in range(len(self.infos))
        ]

        # Calculate the value of the offset frequency, in working machine units,
        # at this time for each dedrifter
        f_offsets_wmu = [int64(0) for _ in self.infos]

        for i in range(len(self.infos)):
            # Calculate the number of steps that should have been performed
            # since the reference time for each dedrifter
            num_steps = int64(
                (now_mu() - self.cache_info.reference_times_mu[i]) // t_step_mu
            )
            f_offsets_wmu[i] = num_steps * self.cache_info.ramp_steps_wmu[i]

            # There's a tiny rounding error here: I don't care

        # Forever more, set the frequency of each AD9910 and update the offset
        while True:
            for i in range(len(self.infos)):
                # Set the frequency of the AD9910
                new_ftw = f_reference_frequencies_mu[
                    i
                ] + self.cache_interface.working_mu_to_FTW(f_offsets_wmu[i])
                self.ad9910s[i].set_mu(ftw=new_ftw)

                # Calculate the new offset frequency
                f_offsets_wmu[i] += self.cache_info.ramp_steps_wmu[i]

            # Wait one timestep
            delay_mu(t_step_mu)
