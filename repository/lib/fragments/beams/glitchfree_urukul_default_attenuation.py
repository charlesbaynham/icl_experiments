import logging

from artiq.coredevice.ad9910 import AD9910
from artiq.coredevice.core import Core
from artiq.coredevice.urukul import urukul_sta_pll_lock
from artiq.language import kernel
from ndscan.experiment import Fragment

logger = logging.getLogger(__name__)


class GlitchFreeUrukulDefaultAttenuation(Fragment):
    """
    Sets the attenuation for an AD9910 / AD9912 channel only if the PLL is
    unlocked (which we take as a proxy for "this AOM has not been set up").

    This is useful when you need to avoid glitches on AOMs (e.g. for injection /
    cavity locks), but need the attenuation to be set up.

    Note that reading the attenuation out from the Urukul is not a solution: the
    read involves clocking zeros into the attenuator shift register then
    clocking the correct value back in. This is followed by an update which
    doesn't change the value, but still causes a brief glitch.

    This could be fixed by someone with dedication and the desire to play with
    gateware. See the lab book entry for 2023-07-04 for more detail:

    https://imperiallondon.sharepoint.com/sites/Srlab-PH/_layouts/OneNote.aspx?id=%2Fsites%2FSrlab-PH%2FShared%20Documents%2FGeneral%2FLab%20books%2FGeneral%20lab%20book%20-%20daily%20log&wd=target%28General.one%7CA4978A3A-3B04-44E2-B4BD-9765E98EC0DB%2F2023-07-04%20Urukul%20glitches%2C%20RED%20MOT%7CC52B1672-85D4-4D2A-9C52-46A9A71362E7%2F%29

    For now though, we make the rule that Urukuls that contain such delicate
    outputs must never have their attenuation initialized by any method other
    than the ones in this Fragment.

    TODO: This could be improved by e.g. writing the current attenuation into
    the Urukul's phase register and reading it back from there. This obviously
    breaks any code which actually uses the phase register, but would be more
    reliable than just hoping for the best. Actually we could use the FTW
    register if we wanted: the AD9910s are controlled through single-tone
    profiles so never actually use the phase register unless we're doing pulse
    shaping, and we can just make sure not to mix and match pulse shaping with
    this Fragment.
    """

    def build_fragment(self, urukul_channel: str, default_attenuation: float):
        self.setattr_device("core")
        self.core: Core

        self.default_attenuation = default_attenuation
        self.urukul_channel = urukul_channel
        self.debug_mode = logger.isEnabledFor(logging.DEBUG)
        self.first_run = True

        # %% Kernel invariants

        kernel_invariants = getattr(self, "kernel_invariants", set())
        self.kernel_invariants = kernel_invariants | {
            "debug_mode",
            "dds",
            "urukul_channel",
            "default_attenuation",
        }

    def host_setup(self):
        self.dds: AD9910 = self.get_device(self.urukul_channel)
        super().host_setup()

    @kernel
    def device_setup(self):
        self.device_setup_subfragments()

        if not self.first_run:
            return

        self.first_run = False

        # Read the status register from the CPLD - we'll use this to detect
        # whether the PLL is locked and treat this as a proxy for "has this DDS
        # been set up already?" so we can avoid glitches from doing it again
        # which might e.g. unlock injected diodes
        self.core.break_realtime()
        cpld = self.dds.cpld  # type: CPLD
        status = cpld.sta_read()

        if urukul_sta_pll_lock(status):
            if self.debug_mode:
                logger.info(
                    "Skipping Urukul attenuation setting - we're assuming it is unchanged from %.1f",
                    self.default_attenuation,
                )

                # Write this attenuation into the python version of the urukul's
                # register so that it's proof against someone writing an
                # attenuation on this urukul elsewhere
                channel = self.dds.chip_select - 4
                att_mu = cpld.att_to_mu(self.default_attenuation)

                att_reg = cpld.att_reg & ~(0xFF << (channel * 8))
                att_reg |= att_mu << (channel * 8)
                cpld.att_reg = att_reg

        else:
            logger.warning(
                "Urukul PLL unlocked - reinitiating DDS and CPLD and setting attenuation to %.1f",
                self.default_attenuation,
            )

            # Initiate the CPLD and DDS. This won't happen again since next time
            # this code runs the PLL will be locked
            self.core.break_realtime()
            self.dds.cpld.init()
            self.dds.init()

            # Start the injection AOM in static mode. Every write to the
            # attenuator (including the write that happens when you just
            # "read"!) caused a small glitch on the output which is enough to
            # unlock IJDs. The proper fix for this is documented in our Onenote
            # 2023-07-04 but hasn't been implemented yet.
            #
            # For now, we just assume that if the PLL is locked then the
            # attenuation has already been set, and we remove the user's ability
            # to change the attenuation. If the attenuation is changed in code,
            # you should power cycle the crate to prompt a reload.
            self.dds.cpld.get_att_mu()  # retrive current attenuation settings for other registers
            self.core.break_realtime()
            self.dds.set_att(self.default_attenuation)

            if self.debug_mode:
                logger.info("Read status register: 0x%X", status)
                logger.info("Urukul PLL status = %s", urukul_sta_pll_lock(status))
