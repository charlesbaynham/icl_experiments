import logging

from artiq.coredevice.core import Core
from artiq.coredevice.ttl import TTLOut
from artiq.language import delay
from artiq.language import delay_mu
from artiq.language import kernel
from artiq.language import now_mu
from artiq.language.core import delay
from artiq.language.core import delay_mu
from artiq.language.core import kernel
from artiq.language.core import now_mu
from artiq.language.core import rpc
from ndscan.experiment import ExpFragment
from ndscan.experiment import make_fragment_scan_exp
from ndscan.experiment.parameters import BoolParam
from ndscan.experiment.parameters import BoolParamHandle
from numpy import int64

from repository.lib import constants
from repository.lib.fragments.relock_falc_toptica import RelockFALCWithWavemeterFrag

logger = logging.getLogger(__name__)

WAND_FAST_LOCK_POLLING = 0.5  # s


class Relock698Frag(RelockFALCWithWavemeterFrag, ExpFragment):
    """
    Relock the 698 to the laser stabilization cavity

    For the 698, this is straightforward
    """

    laser_name_wand = "698"
    laser_name_devicedb = "toptica_698"

    def run_once(self) -> None:
        self.relock()


class _RelockerWith689Shutters(RelockFALCWithWavemeterFrag):
    """
    Provide a method for using the 689 vs. 1379 wavemeter multiplexing shutters
    """

    def build_fragment(self):
        # Get the shutters for the 689 & 1379 wavemeter multiplexing
        self.setattr_device("ttl_shutter_red_wavemeter_689_master")
        self.setattr_device("ttl_shutter_red_wavemeter_689_from_1379")

        self.ttl_shutter_red_wavemeter_689_master: TTLOut
        self.ttl_shutter_red_wavemeter_689_from_1379: TTLOut

        self.setattr_device("core")
        self.core: Core

        return super().build_fragment()

    @kernel
    def set_shutters(self, open_689: bool = True, open_1379: bool = True) -> None:
        """
        Control the shutters for the wavemeter multiplexing.

        These shutters need to be left open in the end, otherwise the 1379 lock
        will not work!

        Args:
            open_689 (bool, optional): Defaults to True.
            open_1379 (bool, optional): Defaults to True.
        """
        self.core.break_realtime()
        self.ttl_shutter_red_wavemeter_689_from_1379.set_o(open_1379)
        delay_mu(int64(self.core.ref_multiplier))
        self.ttl_shutter_red_wavemeter_689_master.set_o(open_689)

        delay(constants.WAND_SHUTTERS_DELAY)  # Wait for closing time

        self.core.wait_until_mu(now_mu())


class Relock689Frag(_RelockerWith689Shutters, ExpFragment):
    """
    Relock the 689 master to the laser stabilization cavity

    To do this, we must handle the shutters for the 689 & 1379 wavemeter
    multiplexing. This will involve blocking the 1379 light, unlocking its PLL.
    So this will need to be relocked next: see :class:`~.Relock1379Frag`.
    """

    laser_name_wand = "689"
    laser_name_devicedb = "toptica_689"

    @rpc(flags={"sync"})
    def relock(self):
        """Convert the relock method to an RPC"""
        return super().relock()

    @kernel
    def relock_from_core(self) -> None:
        self.set_shutters(open_689=True, open_1379=False)
        try:
            self.relock()
        finally:
            self.set_shutters(open_689=True, open_1379=True)

    def run_once(self) -> None:
        self.relock_from_core()


class Relock1379Frag(_RelockerWith689Shutters, ExpFragment):
    """
    Relock the 1379  to the doubled 689 PLL

    Change the WAND exposures before doing the relock, but be sure to change
    them back afterwards
    """

    laser_name_wand = "689"  # We use the same WAND channel as the 689, but multiplex with the shutters
    laser_name_devicedb = "toptica_1379"  # TODO: This is a problem. The WAND steer is still steering the 689 piezo, not the 1379. Obvious in hindsight. Will need to deal with.

    def run_once(self) -> None:
        raise NotImplementedError("This does not work yet. See the comment above")

        self.set_shutters(open_689=False, open_1379=True)

        initial_exposures = self.wand_server.get_laser_db()[self.laser_name_wand][
            "exposure"
        ]

        try:
            self.relock()
        finally:
            for i, ex in enumerate(initial_exposures):
                logger.info(
                    "Resetting %s exposure to %f, %d", self.laser_name_wand, ex, i
                )
                self.wand_server.set_exposure(self.laser_name_wand, ex, i)
            self.set_shutters(open_689=True, open_1379=True)


class SetShutters689Frag(ExpFragment):
    """
    Manually set the 689 and 1379 wavemeter shutters
    """

    def build_fragment(self):
        self.setattr_device("core")
        self.core: Core
        self.setattr_fragment("relocker", Relock689Frag)
        self.relocker: Relock689Frag

        self.setattr_param(
            "open_689",
            BoolParam,
            default=True,
            description="Open the master 689 shutter",
        )
        self.setattr_param(
            "open_1379",
            BoolParam,
            default=True,
            description="Open the doubled 1379 shutter",
        )
        self.open_689: BoolParamHandle
        self.open_1379: BoolParamHandle

    @kernel
    def run_once(self):
        self.relocker.set_shutters(
            open_689=self.open_689.get(), open_1379=self.open_1379.get()
        )


Relock698Cavity = make_fragment_scan_exp(Relock698Frag)
Relock689Cavity = make_fragment_scan_exp(Relock689Frag)
Relock1379Cavity = make_fragment_scan_exp(Relock1379Frag)

SetShutters689 = make_fragment_scan_exp(SetShutters689Frag)
