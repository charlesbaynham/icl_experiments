from typing import List
import logging
import time
import numpy as np

from artiq.coredevice.core import Core
from artiq.master.scheduler import Scheduler
from artiq.coredevice.ad9910 import AD9910

# from artiq.coredevice.ad9912 import AD9912
from artiq.coredevice.urukul import CPLD
from artiq.language.core import kernel, rpc, delay, host_only, delay_mu, at_mu, now_mu
from ndscan.experiment import ExpFragment, Fragment
from ndscan.experiment.entry_point import make_fragment_scan_exp
from ndscan.experiment.parameters import (
    FloatParam,
    FloatParamHandle,
    IntParam,
    IntParamHandle,
)

# from pyaion.fragments.ad9910_ramper import AD9910Ramper

from repository.lib import constants

logger = logging.getLogger(__name__)


class AD9910Dedrifter(Fragment):
    def build_fragment(self, index):
        self.info: constants.DedrifterInfo = constants.dedrifter_infos[index]
        # self.ramper: AD9910Ramper = self.setattr_fragment(
        #     "ramper", AD9910Ramper, self.info.channel_name
        # )
        self.core: Core = self.get_device("core_dedrifter")
        self.dds: AD9910 = self.get_device(self.info.channel_name)

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
            default=self.info.drift_rate,
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

        self.f_start = np.float64(0.0)
        self.f_act = np.float64(0.0)

        kernel_invarints = getattr(self, "kernel_invariants", set())
        self.kernel_invariants = kernel_invarints | {"attenuation", "ramp_rate"}
        # self.f_offset = self.info.reference_frequency

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


class DedrifterFrag(ExpFragment):
    """
    Run dedrifter
    """

    def build_fragment(self):
        self.core: Core = self.get_device("core_dedrifter")

        self.setattr_device("scheduler")
        self.scheduler: Scheduler

        self.cpld: CPLD = self.get_device("urukul_dedrifter_cpld")

        self.dedrifters: List[AD9910Dedrifter] = []

        for i, info in enumerate(constants.dedrifter_infos):
            dedrifter = self.setattr_fragment(
                "dedrifter_{}".format(i), AD9910Dedrifter, i
            )
            self.dedrifters.append(dedrifter)

        self.dedrifter: AD9910Dedrifter = self.dedrifters[0]

        self.setattr_param(
            "wait_time",
            FloatParam,
            description="Time between steps",
            default=100e-3,
            unit="s",
        )
        self.wait_time: FloatParamHandle

        self.setattr_param(
            "n_steps",
            IntParam,
            description="Number of steps",
            default=100,
        )
        self.n_steps: IntParamHandle

        self.write_delay = np.int64(100)

        kernel_invarints = getattr(self, "kernel_invariants", set())
        self.kernel_invariants = kernel_invarints | {"wait_time", "write_delay"}

    @host_only
    def host_setup(self):
        super().host_setup()
        for dedrifter in self.dedrifters:
            dedrifter.f_step = np.float64(
                dedrifter.ramp_rate.get() * self.wait_time.get()
            )
        self.wait_time_mu = self.core.seconds_to_mu(self.wait_time.get())

    @kernel
    def device_setup(self):
        self.core.break_realtime()
        self.cpld.init()
        delay(1e-3)
        self.cpld.cfg_switches(0b1111)
        delay(1e-3)
        self.device_setup_subfragments()

    @rpc
    def check_for_interrupt(self) -> bool:
        if self.scheduler.check_termination():
            name = self.scheduler.expid["class_name"]
            logger.info("Gracefully terminating experiment %s", name)
            return True
        else:
            return False

    @kernel
    def run_once(self):
        # i = 0
        self.core.break_realtime()
        delay(100e-3)

        for dedrifter in self.dedrifters:
            dedrifter.dds.set_att(dedrifter.attenuation.get())
            delay(1e-3)
            dedrifter.f_start = dedrifter.get_offset_freq(verbose=True)
            dedrifter.f_act = dedrifter.f_start
            dedrifter.dds.set(frequency=dedrifter.f_act, phase=0.0, amplitude=1.0)
            delay_mu(self.write_delay)

        # for i in range(self.n_steps.get()):
        while True:
            now = now_mu()
            for dedrifter in self.dedrifters:
                dedrifter.step_freq()
                delay_mu(self.write_delay)
            # i += 1
            # if i > 100:
            #     if self.check_for_interrupt():
            #         break
            #     else:
            #         i = 0
            # delay_mu(self.wait_time_mu)
            at_mu(now + self.wait_time_mu)
        delay(100e-3)
        for dedrifter in self.dedrifters:
            read_freq = dedrifter.dds.get()[0]
            delay(100e-3)
            dedrifter.log_stuff(
                dedrifter.f_act,
                dedrifter.f_step,
                dedrifter.f_start,
                read_freq,
                self.wait_time.get(),
                self.n_steps.get(),
            )
            delay(100e-3)


Dedrifter = make_fragment_scan_exp(DedrifterFrag)
