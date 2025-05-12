import logging
from typing import List

import numpy as np
from artiq.coredevice.core import Core
from artiq.coredevice.urukul import CPLD
from artiq.language.core import at_mu
from artiq.language.core import delay
from artiq.language.core import delay_mu
from artiq.language.core import host_only
from artiq.language.core import kernel
from artiq.language.core import now_mu
from artiq.language.core import rpc
from artiq.master.scheduler import Scheduler
from ndscan.experiment import ExpFragment
from ndscan.experiment.entry_point import make_fragment_scan_exp
from ndscan.experiment.parameters import BoolParam
from ndscan.experiment.parameters import BoolParamHandle
from ndscan.experiment.parameters import FloatParam
from ndscan.experiment.parameters import FloatParamHandle
from ndscan.experiment.parameters import IntParam
from ndscan.experiment.parameters import IntParamHandle

from repository.lib import constants
from repository.lib.fragments.ad9910_dedrifter import AD9910Dedrifter

logger = logging.getLogger(__name__)


class DedriftExpFrag(ExpFragment):
    """
    Dedrift the lasers locked to the ULE cavity.
    """

    def build_fragment(self):
        self.setattr_device("scheduler")
        self.scheduler: Scheduler

        self.cpld: CPLD = self.get_device("urukul0_cpld")

        self.dedrifters: List[AD9910Dedrifter] = []

        self.setattr_param(
            "use_sr_87", BoolParam, description="Use Sr-87?", default=True
        )
        self.use_sr_87: BoolParamHandle

        for i, info in enumerate(constants.dedrifter_infos):
            dedrifter = self.setattr_fragment(
                "dedrifter_{}".format(i), AD9910Dedrifter, dedrifter_info=info
            )
            dedrifter.bind_param("use_sr_87", self.use_sr_87)
            self.dedrifters.append(dedrifter)

        # self.dedrifter: AD9910Dedrifter = self.dedrifters[0]

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

        self.kernel_invariants.add("wait_time")
        self.kernel_invariants.add("write_delay")

    def build(self, fragment_path, *args, **kwargs):
        super().build(fragment_path, *args, **kwargs)

        # Patch "core" attribute to be the dedrifter core
        self.setattr_device("dedrifter_core")
        self.dedrifter_core: Core
        self.core = self.dedrifter_core
        self.kernel_invariants.add("core")

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


DedriftExp = make_fragment_scan_exp(DedriftExpFrag)
