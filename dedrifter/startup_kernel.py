from artiq.coredevice.ad9910 import AD9910
from artiq.coredevice.core import Core
from artiq.coredevice.urukul import CPLD
from artiq.experiment import EnvExperiment
from artiq.language.core import kernel

from repository.lib import constants


class StartupKernel(EnvExperiment):
    """
    Startup kernel to initiate all Urukuls
    """

    def build(self):
        self.setattr_device("core")
        self.core: Core

        device_db = self.get_device_db()

        self.ad9910s: list[AD9910] = []

        for key, desc in device_db.items():
            try:
                if desc["class"] == "AD9910":
                    self.ad9910s.append(self.get_device(key))
            except KeyError:
                pass

        try:
            self.cplds: list[CPLD] = list(
                set([channel.cpld for channel in self.ad9910s])
            )
        except AttributeError:
            # We're building parameters - ignore the error
            self.cplds = []

        self.infos: list[constants.DedrifterInfo] = constants.DEDRIFTER_INFOS
        self.kernel_invariants.add("infos")

    @kernel
    def run(self):
        self.core.reset()
        core_log("Initiating CPLDs")

        for cpld in self.cplds:
            self.core.break_realtime()
            cpld.init()

        core_log("Initiating AD9910s")

        for ad9910 in self.ad9910s:
            self.core.break_realtime()
            ad9910.init()

        core_log("Setting AD9910 attenuators and RF switches")
        for i in range(len(self.infos)):
            info = self.infos[i]
            ad9910 = self.ad9910s[i]

            self.core.break_realtime()
            ad9910.set_att(info.attenuation)

            # Intentionally leave the RF switch off - the idle kernel will turn
            # it on only if the config is correct, so we can tell at a glance if
            # the dedrifter is running

        core_log("Startup kernel finished")
