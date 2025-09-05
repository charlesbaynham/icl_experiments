import logging

from artiq.coredevice.adf5356 import ADF5356
from artiq.coredevice.core import Core
from artiq.coredevice.mirny import Mirny
from artiq.language import delay
from artiq.language import kernel
from artiq.language import now_mu
from ndscan.experiment import Fragment
from ndscan.experiment.parameters import BoolParam
from ndscan.experiment.parameters import BoolParamHandle
from ndscan.experiment.parameters import FloatParam
from ndscan.experiment.parameters import FloatParamHandle

from repository.lib import constants

logger = logging.getLogger(__name__)

TRANSFER_CAVITY_MIRNY_SETTINGS_87 = [
    x
    for x in constants.MIRNY_SETTINGS_87
    if x.device_name == "mirny_eom_transfer_cavity_offset"
][0]
TRANSFER_CAVITY_MIRNY_SETTINGS_88 = [
    x
    for x in constants.MIRNY_SETTINGS_88
    if x.device_name == "mirny_eom_transfer_cavity_offset"
][0]

assert (
    TRANSFER_CAVITY_MIRNY_SETTINGS_87.device_name
    == TRANSFER_CAVITY_MIRNY_SETTINGS_88.device_name
)


class TransferCavityFrag(Fragment):
    """
    Steer the transfer cavity lock if requested, but prefer not to

    This fragment allows changing the 461 lock point but will not do so
    unless it has been changed since the last point.
    """

    def build_fragment(self):
        self.kernel_invariants = getattr(self, "kernel_invariants", set())

        self.setattr_device("core")
        self.core: Core

        self.setattr_param(
            "detuning_461",
            FloatParam,
            "Detuning of 461 transfer cavity",
            default=0.0,
            unit="MHz",
        )
        self.detuning_461: FloatParamHandle

        self.setattr_param(
            "delay_relock",
            FloatParam,
            "Time to wait for relock after changing frequency",
            default=1.0,
            unit="s",
        )
        self.delay_relock: FloatParamHandle

        self.setattr_param(
            "sr87",
            BoolParam,
            "True = sr87, false = sr88",
            default=constants.USE_SR87,  # TODO: make sure this gets set properly
        )
        self.sr87: BoolParamHandle

        self.debug_mode = logger.isEnabledFor(logging.DEBUG)

        self.kernel_invariants.add("debug_mode")

        self.previous_freq = 0.0
        self.first_run = True

    def host_setup(self):
        super().host_setup()

        self.mirny_channel: ADF5356 = self.get_device(
            TRANSFER_CAVITY_MIRNY_SETTINGS_87.device_name
        )
        self.kernel_invariants.add("mirny_channel")

        self.mirny_cpld: Mirny = self.mirny_channel.cpld
        self.kernel_invariants.add("mirny_cpld")

        self.mirny_settings = (
            TRANSFER_CAVITY_MIRNY_SETTINGS_87
            if self.sr87.get()
            else TRANSFER_CAVITY_MIRNY_SETTINGS_88
        )

    @kernel
    def device_setup(self) -> None:
        self.device_setup_subfragments()

        new_freq = self.mirny_settings.frequency + self.detuning_461.get()

        if self.first_run:
            self.first_run = False

            # Assume that the frequency has not been changed from the nominal
            # for now: once the relocker is more reliable we should not do this
            self.previous_freq = self.mirny_settings.frequency

            # Initiate the channel and CPLD on the first run if the PLL is not
            # already locked
            self.core.break_realtime()
            pll_locked = self.mirny_channel.read_muxout()

            if not pll_locked:
                self.core.break_realtime()
                self.mirny_cpld.init()
                self.core.break_realtime()
                self.mirny_channel.init()

                # Set the 461 frequency once
                self.core.break_realtime()
                self.set_offset_and_wait_for_relock(new_freq)

        else:
            # If it changed since last time, update it.
            if new_freq != self.previous_freq:
                self.core.break_realtime()
                self.set_offset_and_wait_for_relock(new_freq)

    @kernel
    def set_offset_and_wait_for_relock(self, new_freq: float) -> None:
        self.mirny_channel.set_frequency(new_freq)

        # TODO: Check if the relock succeeded instead of just waiting
        delay(self.delay_relock.get())

        self.previous_freq = new_freq

        self.core.wait_until_mu(now_mu())
