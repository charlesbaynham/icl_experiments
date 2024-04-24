from typing import *

from artiq.coredevice.ad9910 import AD9910
from artiq.coredevice.ad9912 import AD9912
from artiq.coredevice.urukul import CPLD
from artiq.experiment import parallel
from ndscan.experiment import *


def make_urukul_init(names: List[str]):
    class UrukulInitInstance(UrukulInit):
        channel_names = names

    return UrukulInitInstance


class UrukulInit(Fragment):
    """
    Simple fragment to ensure that all urukul channels are initted correctly
    """

    channel_names: List[str] = []

    initiated_channels = set()

    def build_fragment(self):
        # Get our AD9910 and AD9912s
        devices = [self.get_device(d) for d in self.channel_names]

        self.ad9910s: List[AD9910] = list(filter(lambda d: isinstance(d, AD9910)))
        self.ad9912s: List[AD9912] = list(filter(lambda d: isinstance(d, AD9912)))

        assert len(self.ad9910s) + len(self.ad9912s) == len(
            devices
        ), "Non-ad9910 or ad9912 passed"

        # Get associated urukuls for each, removing duplicates
        self.urukuls: List[CPLD] = [d.cpld for d in self.ad9910s + self.ad9912s]
        self.urukuls = list(set(self.urukuls))

        # Get unique IDs for each. These come from the devices in the device
        # manager and so are common to different invocations of this fragment.
        self.ad9910_ids = [hash(d) for d in self.ad9910s]
        self.ad9912_ids = [hash(d) for d in self.ad9912s]
        self.urukul_ids = [hash(d) for d in self.urukuls]

        self.first_run = True

    @kernel
    def device_setup(self) -> None:
        if self.first_run:
            self.first_run = False

            # Initiate any suservo CPLDs which haven't already been initiated
            with parallel:
                for i in range(len(self.urukuls)):
                    urukul = self.urukuls[i]

                    if not self.mark_initiated(self.urukul_ids[i]):
                        urukul.init()

            # Then do the AD9910s
            with parallel:
                for i in range(len(self.ad9910s)):
                    ad9910 = self.ad9910s[i]

                    if not self.mark_initiated(self.ad9910_ids[i]):
                        ad9910.init()

            # ... and 12s
            with parallel:
                for i in range(len(self.ad9912s)):
                    ad9912 = self.ad9912s[i]

                    if not self.mark_initiated(self.ad9912_ids[i]):
                        ad9912.init()

        self.device_setup_subfragments()

    @rpc
    def mark_initiated(self, channel_number: TInt32) -> TBool:
        """
        Check whether the given device has been initiated and return True if it
        has. In either case, mark it as now having been initiated

        This funcation accepts ints, so you must pass the channel associated
        with the device you are querying.

        This is an RPC so that we can use python features like class members to
        communicate between instances. This could be done purely on the core
        using e.g. a singleton class, but that's more complex. Here I'll pay the
        few ms penalty for keeping the code simpler.
        """
        out = channel_number in self.__class__.initiated_channels
        self.__class__.initiated_channels.add(channel_number)
        return out
