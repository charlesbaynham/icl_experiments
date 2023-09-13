import logging
from typing import List

from artiq.coredevice.ad9910 import AD9910
from artiq.coredevice.core import Core
from artiq.experiment import delay
from artiq.experiment import kernel
from artiq.experiment import TFloat
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
from repository.lib.fragments.glitchfree_urukul_default_attenuation import (
    GlitchFreeUrukulDefaultAttenuation,
)
from repository.lib.fragments.suservo import LibSetSUServoStatic


logger = logging.getLogger(__name__)

RED_BEAM_INFOS = [
    constants.AOM_BEAMS[beam]
    for beam in [
        "red_mot_diagonal",
        "red_mot_sigmaplus",
        "red_mot_sigmaminus",
    ]
]


class RedBeamSetter(SetBeamsToDefaults):
    default_beam_infos = RED_BEAM_INFOS


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

        self.setattr_fragment(
            "GlitchFreeUrukulDefaultAttenuation",
            GlitchFreeUrukulDefaultAttenuation,
            "urukul9910_aom_doublepass_689_red_injection",
            constants.RED_INJECTION_AOM_ATTENUATION,
        )
        self.GlitchFreeUrukulDefaultAttenuation: GlitchFreeUrukulDefaultAttenuation

        self.suservo_nominal_amplitudes: List[float] = []
        self.suservo_fragments: List[LibSetSUServoStatic] = []
        for beam_info in RED_BEAM_INFOS:
            f = self.setattr_fragment(
                "suservofrag_" + beam_info.name,
                LibSetSUServoStatic,
                channel=beam_info.suservo_device,
            )
            self.suservo_fragments.append(f)
            self.suservo_nominal_amplitudes.append(beam_info.setpoint)

        # Commented out since the cavity EOM is currently driven by a Rigol
        # self.setattr_fragment("laser_stab_system", LaserStabilisationSystem)
        # self.laser_stab_system: LaserStabilisationSystem

        # %% DEVICES

        self.setattr_device("urukul9910_aom_doublepass_689_red_injection")
        self.injection_aom: AD9910 = self.urukul9910_aom_doublepass_689_red_injection

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
            "injection_aom_static_detuning",
            FloatParam,
            "Detuning of 689 injection AOM static frequency from nominal",
            unit="MHz",
            default=0.0,
        )
        self.injection_aom_static_detuning: FloatParamHandle

        self.setattr_param(
            "ramp_frequency",
            FloatParam,
            "689 injection AOM ramp frequency",
            unit="kHz",
            default=constants.RED_INJECTION_AOM_RAMP_FREQUENCY,
        )
        self.setattr_param(
            "ramp_lower_detuning",
            FloatParam,
            "Detuning of 689 injection AOM from nominal frequency at lowest point of ramp",
            unit="MHz",
            default=0.0,
        )
        self.setattr_param(
            "ramp_upper_detuning",
            FloatParam,
            "Detuning of 689 injection AOM from nominal frequency at highest point of ramp",
            unit="MHz",
            default=3e6,
        )
        self.setattr_param(
            "ramp_type",
            IntParam,
            "689 injection AOM ramp type (0=triangle,1=positive-saw,2=negative-saw)",
            default=2,
        )

        self.ramp_frequency: FloatParamHandle
        self.ramp_lower_detuning: FloatParamHandle
        self.ramp_upper_detuning: FloatParamHandle
        self.ramp_type: IntParamHandle

        # %% Kernel parameters

        # Initialised here so that it's available across kernels, but calculated
        # in device_setup in case it's varied in a scan
        self.ramp_rate = 0.0

        self.debug_mode = logger.isEnabledFor(logging.DEBUG)

        # %% Kernel invariants
        kernel_invariants = getattr(self, "kernel_invariants", set())
        self.kernel_invariants = kernel_invariants | {
            "debug_mode",
        }

    def host_setup(self):
        super().host_setup()
        assert self.ramp_type.get() in [0, 1, 2], "Ramp type must be 0, 1 or 2"

    @kernel
    def device_setup(self):
        self.device_setup_subfragments()

        # Precalculate the ramp rate required to get the requested modulation frequency
        self.ramp_rate = abs(
            (self.ramp_lower_detuning.get() - self.ramp_upper_detuning.get())
            * self.ramp_frequency.get()
        )

        if self.ramp_type.get() == 0:
            # Triangle waves will need to ramp twice as quickly
            self.ramp_rate *= 2

        if self.debug_mode:
            logger.info(
                "Calculated required ramp_rate = %s kHz/s", self.ramp_rate * 1e-3
            )

        self.core.break_realtime()

        # Ensure the RF switch is on and the frequency is correct.
        # These are glitch free, so we do them each time
        self.injection_aom.set(
            constants.RED_INJECTION_AOM_FREQUENCY
            + self.injection_aom_static_detuning.get()
        )
        self.injection_aom.cfg_sw(True)
        self.injection_aom.sw.on()

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
    def turn_on_mot_beams(self, ignore_shutters=False):
        return self.all_mot_beams_setter.turn_beams_on(ignore_shutters)

    @kernel
    def turn_off_mot_beams(self, ignore_shutters=False):
        return self.all_mot_beams_setter.turn_beams_off(ignore_shutters)

    @kernel
    def start_ramping_red(self):
        """
        Start modulation of the 689 DDS as configured
        """

        self.injection_aom_ramper.start_ramp(
            self.ramp_rate,
            self.ramp_lower_detuning.get() + constants.RED_INJECTION_AOM_FREQUENCY,
            self.ramp_upper_detuning.get() + constants.RED_INJECTION_AOM_FREQUENCY,
            self.ramp_type.get(),
        )

    @kernel
    def stop_ramping_red(self, freq=0.0):
        """
        Stop modulation of the 689 DDS and return to static (or specified) frequency
        """
        self.injection_aom_ramper.stop_ramp()

        if freq == 0.0:
            self.injection_aom.set_frequency(
                self.injection_aom_static_detuning.get()
                + constants.RED_INJECTION_AOM_FREQUENCY
            )
        else:
            self.injection_aom.set_frequency(freq)

    @kernel
    def set_mot_detuning(self, detuning: TFloat):
        """Set the detuning of the MOT beams from the static frequency

        Does not affect ramp settings and so will have no effect if ramping is
        enabled.

        This method advances the timeline by the duration of an AD9910 SPI
        transaction.

        Args:
            detuning (float): Detuning in Hz
        """
        freq = (
            constants.RED_INJECTION_AOM_FREQUENCY
            + self.injection_aom_static_detuning.get()
            + detuning
        )

        if self.debug_mode:
            logger.info(
                "Setting AOM detuning to %.3f kHz = %.6f MHz on %s",
                detuning * 1e-3,
                freq * 1e-6,
                self.injection_aom,
            )

        self.injection_aom.set(freq)

    @kernel
    def set_mot_suservo_amplitude(self, amplitude_multiple: TFloat):
        """
        Set the SUServo target amplitudes of all MOT beams

        Args:
            amplitude_multiple (TFloat): Amplitude of MOT beams, expressed as a multiple of the nominal amplitude
        """

        for i in range(len(self.suservo_fragments)):

            suservo_frag = self.suservo_fragments[i]
            nominal_setpoint = self.suservo_nominal_amplitudes[i]

            setpoint = nominal_setpoint * amplitude_multiple

            if self.debug_mode:
                logger.info(
                    "Setting %s setpoint to %.2 x nom = %.3f V",
                    suservo_frag,
                    amplitude_multiple,
                    setpoint,
                )

            suservo_frag.set_setpoint(setpoint)
