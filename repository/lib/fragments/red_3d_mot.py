import logging

from artiq.coredevice.ad9910 import AD9910
from artiq.coredevice.core import Core
from artiq.coredevice.urukul import CPLD
from artiq.coredevice.urukul import urukul_sta_pll_lock
from artiq.experiment import delay
from artiq.experiment import kernel
from ndscan.experiment import Fragment
from ndscan.experiment.parameters import FloatParam
from ndscan.experiment.parameters import FloatParamHandle
from ndscan.experiment.parameters import IntParam
from ndscan.experiment.parameters import IntParamHandle
from pyaion.fragments.beam_setter import ControlBeamsWithoutCoolingAOM

import repository.lib.constants as constants
from repository.lib.fragments.ad9910_ramper import AD9910Ramper
from repository.lib.fragments.beam_setters import SetBeamsToDefaults
from repository.lib.fragments.cavity_control import LaserStabilisationSystem


logger = logging.getLogger(__name__)


class RedBeamSetter(SetBeamsToDefaults):
    beam_infos = [
        constants.AOM_BEAMS[beam]
        for beam in [
            "red_mot_diagonal",
            "red_mot_sigmaplus",
            "red_mot_sigmaminus",
        ]
    ]


class Red3DMOTFrag(Fragment):
    """
    Methods for making and controlling the red 3D MOT
    """

    def build_fragment(self):
        self.setattr_device("core")
        self.core: Core

        # %% FRAGMENTS

        self.setattr_fragment("all_beam_default_setter", RedBeamSetter)
        self.all_beam_default_setter: SetBeamsToDefaults

        self.setattr_fragment(
            "all_mot_beams_setter",
            ControlBeamsWithoutCoolingAOM,
            beam_infos=[
                constants.AOM_BEAMS["red_mot_diagonal"],
                constants.AOM_BEAMS["red_mot_sigmaplus"],
                constants.AOM_BEAMS["red_mot_sigmaminus"],
            ],
        )
        self.all_mot_beams_setter: ControlBeamsWithoutCoolingAOM

        self.setattr_fragment(
            "injection_aom_ramper",
            AD9910Ramper,
            "urukul9910_aom_doublepass_689_red_injection",
        )
        self.injection_aom_ramper: AD9910Ramper

        self.setattr_fragment("laser_stab_system", LaserStabilisationSystem)
        self.laser_stab_system: LaserStabilisationSystem

        # %% DEVICES

        self.injection_aom: AD9910 = self.get_device(
            "urukul9910_aom_doublepass_689_red_injection"
        )

        # %% PARAMETERS

        self.setattr_param(
            "chamber_2_field_gradient",
            FloatParam,
            "Field gradient current for chamber 2",
            default=constants.B_FIELD_GRADIENT,
            unit="A",
            min=0,
            max=100,
        )
        self.chamber_2_field_gradient: FloatParamHandle

        self.setattr_param(
            "injection_aom_static_frequency",
            FloatParam,
            "689 injection AOM static frequency",
            unit="MHz",
            default=constants.RED_INJECTION_AOM_FREQUENCY,
        )
        self.injection_aom_static_frequency: FloatParamHandle

        self.setattr_param(
            "ramp_frequency",
            FloatParam,
            "689 injection AOM ramp frequency",
            unit="MHz",
            default=1e6,
        )
        self.setattr_param(
            "ramp_low",
            FloatParam,
            "689 injection AOM ramp lower limit",
            unit="MHz",
            default=constants.RED_INJECTION_AOM_FREQUENCY,
        )
        self.setattr_param(
            "ramp_high",
            FloatParam,
            "689 injection AOM ramp upper limit",
            unit="MHz",
            default=constants.RED_INJECTION_AOM_FREQUENCY + 2e6,
        )
        self.setattr_param(
            "ramp_type",
            IntParam,
            "689 injection AOM ramp type (0=triangle,1=positive-saw,2=negative-saw)",
            default=0,
        )

        self.ramp_frequency: FloatParamHandle
        self.ramp_low: FloatParamHandle
        self.ramp_high: FloatParamHandle
        self.ramp_type: IntParamHandle

        self.ramp_rate = 0.0
        self.debug_mode = logger.isEnabledFor(logging.DEBUG)

    def host_setup(self):
        super().host_setup()
        assert self.ramp_type.get() in [0, 1, 2], "Ramp type must be 0, 1 or 2"

    @kernel
    def device_setup(self):
        self.device_setup_subfragments()

        # Precalculate the ramp rate required to get the requested modulation frequency
        self.ramp_rate = (
            self.ramp_high.get() - self.ramp_low.get()
        ) * self.ramp_frequency.get()

        if self.ramp_type.get() == 0:
            # Triangle waves will need to ramp twice as quickly
            self.ramp_rate *= 2

        self.core.break_realtime()

        # Ensure the RF switch is on and the frequency is correct.
        # These are glitch free, so we do them each time
        self.injection_aom.set(self.injection_aom_static_frequency.get())
        self.injection_aom.cfg_sw(True)
        self.injection_aom.sw.on()

        # Read the status register from the CPLD - we'll use this to detect
        # whether the PLL is locked and treat this as a proxy for "has this DDS
        # been set up already?" so we can avoid glitches from doing it again
        # which might e.g. unlock injected diodes
        status = self.injection_aom.cpld.sta_read()

        if urukul_sta_pll_lock(status):
            if self.debug_mode:
                logger.info(
                    "Skipping Urukul attenuation setting - we're assuming it is unchanged from %.1f",
                    constants.RED_INJECTION_AOM_ATTENUATION,
                )
        else:
            logger.warning(
                "Urukul PLL unlocked - reinitiating DDS and CPLD and setting attenuation to %.1f",
                constants.RED_INJECTION_AOM_ATTENUATION,
            )

            # Initiate the CPLD and DDS. This won't happen again since next time
            # this code runs the PLL will be locked
            self.core.break_realtime()
            self.injection_aom.cpld.init()
            self.injection_aom.init()

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
            self.injection_aom.cpld.get_att_mu()  # retrive current attenuation settings for other registers
            self.injection_aom.set_att(constants.RED_INJECTION_AOM_ATTENUATION)

            if self.debug_mode:
                logger.info("Read status register: 0x%X", status)
                logger.info("Urukul PLL status = %s", urukul_sta_pll_lock(status))

    @kernel
    def init(self):
        """
        Set up beam state for the red MOT, i.e. set up AOMs and close all shutters

        This is not in device_setup so that the user can choose when / whether to call it during each scan cycle
        """
        # Turn on all the AOMs but close all the shutters
        self.all_beam_default_setter.turn_on_all(shutter_state=False)

        # Make sure that the shutters are closed before run_once starts
        delay(self.all_beam_default_setter.get_max_shutter_delay())

    @kernel
    def turn_on_mot_beams(self):
        self.all_mot_beams_setter.turn_beams_on()

    @kernel
    def turn_off_mot_beams(self):
        self.all_mot_beams_setter.turn_beams_off()

    @kernel
    def start_ramping_red(self):
        """
        Start modulation of the 689 DDS as configured
        """

        self.injection_aom_ramper.start_ramp(
            self.ramp_rate,
            self.ramp_low.get(),
            self.ramp_high.get(),
            self.ramp_type.get(),
        )

    @kernel
    def stop_ramping_red(self):
        """
        Stop modulation of the 689 DDS and return to default frequency
        """
        self.injection_aom_ramper.stop_ramp()
        self.injection_aom.set_frequency(self.injection_aom_static_frequency.get())
