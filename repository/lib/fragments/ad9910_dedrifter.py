import logging
import time

import numpy as np
from artiq.coredevice.ad9910 import AD9910
from artiq.coredevice.core import Core
from artiq.language.core import kernel
from artiq.language.core import rpc
from ndscan.experiment import Fragment
from ndscan.experiment.parameters import BoolParam
from ndscan.experiment.parameters import BoolParamHandle
from ndscan.experiment.parameters import FloatParam
from ndscan.experiment.parameters import FloatParamHandle
from ndscan.experiment.parameters import IntParam
from ndscan.experiment.parameters import IntParamHandle

from repository.lib.constants import DedrifterInfo

logger = logging.getLogger(__name__)


class AD9910Dedrifter(Fragment):
    def build_fragment(self, dedrifter_info: DedrifterInfo):
        self.info = dedrifter_info

        self.setattr_device("dedrifter_core")
        self.dedrifter_core: Core

        # Patch "core" attribute to be the dedrifter core
        self.core: Core = self.dedrifter_core
        self.kernel_invariants = getattr(self, "kernel_invariants", set())
        self.kernel_invariants.add("core")

        self.dds: AD9910 = self.get_device(self.info.channel_name)
        self.kernel_invariants.add("dds")

        name = self.info.laser_name

        self.setattr_param(
            "f_offset",
            FloatParam,
            description=f"Offset {name}",
            default=self.info.reference_frequency,
            unit="MHz",
        )
        self.f_offset: FloatParamHandle

        self.setattr_param(
            "reference_time",
            IntParam,
            description=f"Reference (Unix) time {name}",
            default=self.info.reference_time,
            unit="s",
        )
        self.reference_time: IntParamHandle

        self.setattr_param(
            "ramp_rate",
            FloatParam,
            description=f"Ramp rate {name}",
            default=self.info.ramp_rate,
            unit="Hz/s",
            scale=1,
        )
        self.ramp_rate: FloatParamHandle

        self.setattr_param(
            "attenuation",
            FloatParam,
            description=f"Attenuation {name}",
            default=0.0,
            unit="dB",
        )
        self.attenuation: FloatParamHandle

        self.setattr_param(
            "use_sr_87", BoolParam, description="Use Sr-87?", default=True
        )
        self.use_sr_87: BoolParamHandle

        self.kernel_invariants.add("attenuation")
        self.kernel_invariants.add("ramp_rate")

        # Kernel vars
        self.f_start = np.float64(0.0)
        self.f_act = np.float64(0.0)

    # @host_only
    # def host_setup(self):
    #     super().host_setup()
    #     self.f_act = self.f_offset.get()

    @rpc
    def get_offset_freq(self, verbose=False) -> float:  # -> Any | float:  # -> float:
        ref_time = self.reference_time.get()
        if ref_time == 0:
            t_diff = 0.0
        else:
            t_diff = time.time() - ref_time
        f_offset: float = self.f_offset.get() + t_diff * self.ramp_rate.get()
        if not self.use_sr_87.get():
            f_offset = self.info.isotope_shift - f_offset
        if verbose:
            logger.info("Laser: %s", self.info.laser_name)
            logger.info("Seconds since last calibration: %f s", t_diff)
            logger.info("Days since last calibration: %f days", t_diff / 86400)
            logger.info("Reference offset: %f MHz", self.f_offset.get() / 1e6)
            logger.info("Drift-compensated offset: %f MHz", f_offset / 1e6)
            logger.info("=" * 20)
        return f_offset

    @kernel
    def device_setup(self):
        self.core.break_realtime()
        self.dds.init()
        self.device_setup_subfragments()

    @kernel
    def step_freq(self):
        self.f_act += self.f_step
        self.dds.set(frequency=self.f_act, phase=0.0, amplitude=1.0)

    @rpc(flags={"async"})
    def log_stuff(self, f_act, f_step, f_start, read_freq, wait_time, n_steps):
        logger.info("Laser: %s", self.info.laser_name)
        logger.info("f_step = %f", f_step)
        logger.info("the last set frequency was %f", f_act)
        logger.info("the read frequency is      %f", read_freq)
        logger.info(
            "I expect the frequency to have changed by %f",
            self.ramp_rate.get() * wait_time * n_steps,
        )
        logger.info(
            "It has changed by                         %f",
            read_freq - f_start,
        )
        logger.info("=" * 20)
