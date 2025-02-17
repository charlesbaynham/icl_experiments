from typing import List
import logging
import time
import numpy as np

from artiq.coredevice.core import Core
from artiq.master.scheduler import Scheduler
from artiq.coredevice.ad9910 import AD9910

# from artiq.coredevice.ad9912 import AD9912
from artiq.coredevice.urukul import CPLD
from artiq.language.core import kernel, rpc, delay, delay_mu, at_mu, now_mu
from artiq.language.environment import EnvExperiment, HasEnvironment
from artiq.language.environment import NumberValue

# from pyaion.fragments.ad9910_ramper import AD9910Ramper

from repository.lib import constants

logger = logging.getLogger(__name__)

core_name = "core_dedrifter"


class AD9910Dedrifter(HasEnvironment):

    def build(self, index: int = 0):
        self.core_dedrifter: Core = self.get_device(core_name)
        self.info: constants.DedrifterInfo = constants.dedrifter_infos[index]

        self.laser_name = self.info.laser_name
        self.channel_name = self.info.channel_name
        self.dds: AD9910 = self.get_device(self.channel_name)

        self.setattr_argument(
            f"f_offset_{self.laser_name}",
            NumberValue(self.info.reference_frequency, unit="MHz"),
            group=self.laser_name,
        )

        self.setattr_argument(
            f"reference_time_{self.laser_name}",
            NumberValue(self.info.reference_time, unit="s"),
            group=self.laser_name,
        )

        self.setattr_argument(
            f"ramp_rate_{self.laser_name}",
            NumberValue(self.info.drift_rate, unit="Hz/s", scale=1),
            group=self.laser_name,
        )

        self.setattr_argument(
            f"attenuation_{self.laser_name}",
            NumberValue(0.0, unit="dB", scale=1),
            group=self.laser_name,
        )

        self.ref_time: float = getattr(self, f"reference_time_{self.laser_name}")
        self.ramp_rate: float = getattr(self, f"ramp_rate_{self.laser_name}")
        self.f_offset: float = getattr(self, f"f_offset_{self.laser_name}")
        self.attenuation: float = getattr(self, f"attenuation_{self.laser_name}")

        self.f_start = np.float64(0.0)
        self.f_act = np.float64(0.0)
        self.f_step = np.float64(0.0)

    @rpc
    def get_offset_freq(self, verbose=False) -> float:  # -> Any | float:  # -> float:
        if self.ref_time == 0:
            t_diff = 0.0
        else:
            t_diff = time.time() - self.ref_time
        f_offset: float = f_offset + t_diff * self.ramp_rate
        if verbose:
            logger.info("Laser: %s", self.info.laser_name)
            logger.info("Seconds since last calibration: %f s", t_diff)
            logger.info("Days since last calibration: %f days", t_diff / 86400)
            logger.info("Reference offset: %f MHz", self.f_offset() / 1e6)
            logger.info("Drift-compensated offset: %f MHz", f_offset / 1e6)
            logger.info("=" * 20)
        return f_offset

    @kernel(arg=core_name)
    def init(self):
        self.dds.init()

    @kernel(arg=core_name)
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


class DedrifterExp(EnvExperiment):
    """
    Dedrifter
    """

    core_name = "core_dedrifter"

    def build(self):
        self.core_dedrifter: Core = self.get_device(core_name)

        self.setattr_device("scheduler")
        self.scheduler: Scheduler

        self.cpld: CPLD = self.get_device("urukul_dedrifter_cpld")

        self.dedrifter_infos = constants.dedrifter_infos
        self.dedrifter_names = [info.channel_name for info in self.dedrifter_infos]

        self.f_act_list = [0.0, 0.0]
        self.f_step_list = [0.0, 0.0]

        self.dedrifters: list[AD9910Dedrifter] = []

        for i in range(len(constants.dedrifter_infos)):
            self.dedrifters.append(AD9910Dedrifter(self, index=i))

        self.setattr_argument("wait_time", NumberValue(100e-3, unit="s"))
        self.wait_time: float
        self.setattr_argument("n_steps", NumberValue(0, precision=0, scale=1))
        self.n_steps: int

        self.write_delay = np.int64(100)
        self.wait_time_mu = np.int64(0)

    @kernel(arg=core_name)
    def run(self):
        self.get_wait_mu()
        self.init_devices()
        for dedrifter in self.dedrifters:
            dedrifter.dds.set_att(dedrifter.attenuation.get())
            delay(1e-3)
            dedrifter.f_start = dedrifter.get_offset_freq(verbose=True)
            dedrifter.f_act = dedrifter.f_start
            dedrifter.dds.set(frequency=dedrifter.f_act, phase=0.0, amplitude=1.0)
            delay_mu(self.write_delay)

        while True:
            now = now_mu()
            for dedrifter in self.dedrifters:
                dedrifter.step_freq()
                delay_mu(self.write_delay)
            at_mu(now + self.wait_time_mu)

    @rpc
    def get_wait_mu(self):
        for dedrifter in self.dedrifters:
            dedrifter.f_step = np.float64(
                dedrifter.ramp_rate.get() * self.wait_time.get()
            )
        self.wait_time_mu = self.core_dedrifter.seconds_to_mu(self.wait_time.get())

    @kernel(arg=core_name)
    def init_devices(self):
        self.core_dedrifter.break_realtime()
        self.cpld.init()
        delay(1e-3)
        self.cpld.cfg_switches(0b1111)
        delay(1e-3)
        for dedrifter in self.dedrifters:
            dedrifter.init()

    @rpc
    def check_for_interrupt(self) -> bool:
        if self.scheduler.check_termination():
            name = self.scheduler.expid["class_name"]
            logger.info("Gracefully terminating experiment %s", name)
            return True
        else:
            return False
