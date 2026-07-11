import logging

from artiq.coredevice.ad9910 import AD9910
from artiq.coredevice.core import Core
from artiq.coredevice.ttl import TTLOut
from artiq.experiment import TFloat
from artiq.language import delay
from artiq.language import delay_mu
from artiq.language import kernel
from ndscan.experiment import Fragment
from ndscan.experiment.parameters import BoolParam
from ndscan.experiment.parameters import BoolParamHandle
from ndscan.experiment.parameters import FloatParam
from ndscan.experiment.parameters import FloatParamHandle
from ndscan.experiment.parameters import IntParam
from ndscan.experiment.parameters import IntParamHandle
from numpy import int64
from pyaion.fragments.ad9910_ramper import AD9910Ramper
from pyaion.fragments.default_beam_setter import SetBeamsToDefaults
from pyaion.fragments.default_beam_setter import make_set_beams_to_default
from pyaion.fragments.suservo import LibSetSUServoStatic
from pyaion.fragments.toggle_beams_with_AOM_and_shutter import (
    ControlBeamsWithoutCoolingAOM,
)

import repository.lib.constants as constants
from repository.lib.fragments.beams.glitchfree_urukul_default_attenuation import (
    GlitchFreeUrukulDefaultAttenuation,
)

logger = logging.getLogger(__name__)

RED_SUSERVO_INFOS = [
    constants.SUSERVOED_BEAMS[beam]
    for beam in [
        "red_mot_diagonal",
        "red_mot_sigmaplus",
        "red_mot_sigmaminus",
        "red_up",
    ]
]

# Module-level so every RedBeamController instance shares one class; a single
# kernel touching two of them (e.g. a qbutler DAG fix) can then unify the
# all_beam_default_setter attribute.
RedBeamSettings = make_set_beams_to_default(
    suservo_beam_infos=RED_SUSERVO_INFOS,
    name="RedBeamSettings",
)


class RedBeamController(Fragment):
    """
    Methods for making and controlling the red beams in chamber 2
    """

    def build_fragment(self):
        self.kernel_invariants = getattr(self, "kernel_invariants", set())
        self.setattr_device("core")
        self.core: Core

        # %% FRAGMENTS

        # Setup of defaults for all beams
        self.setattr_fragment("all_beam_default_setter", RedBeamSettings)
        self.all_beam_default_setter: SetBeamsToDefaults

        # Interface for AOM + shutter toggling of mot beams
        self.setattr_fragment(
            "all_mot_beams_setter",
            ControlBeamsWithoutCoolingAOM,
            beam_infos=RED_SUSERVO_INFOS,
        )
        self.all_mot_beams_setter: ControlBeamsWithoutCoolingAOM

        # Quick togglers for just the sigmaplus / sigmaminus beams, for pumping
        self.setattr_fragment(
            "sigmaplus_toggler",
            ControlBeamsWithoutCoolingAOM,
            beam_infos=[constants.SUSERVOED_BEAMS["red_mot_sigmaplus"]],
        )
        self.sigmaplus_toggler: ControlBeamsWithoutCoolingAOM

        self.setattr_fragment(
            "sigmaminus_toggler",
            ControlBeamsWithoutCoolingAOM,
            beam_infos=[constants.SUSERVOED_BEAMS["red_mot_sigmaminus"]],
        )
        self.sigmaminus_toggler: ControlBeamsWithoutCoolingAOM

        _, s = self.all_beam_default_setter.get_setpoints_beaminfo_setters()[
            "red_mot_sigmaplus"
        ]
        self.sigmaplus_setpoint_handle: FloatParamHandle = s.setpoint_handle
        self.sigmaplus_setpoint_setter: LibSetSUServoStatic = s.setter

        _, s = self.all_beam_default_setter.get_setpoints_beaminfo_setters()[
            "red_mot_sigmaminus"
        ]
        self.sigmaminus_setpoint_handle: FloatParamHandle = s.setpoint_handle
        self.sigmaminus_setpoint_setter: LibSetSUServoStatic = s.setter

        # Fast ramping of the AD9910 controlling the injection AOM
        self.setattr_fragment(
            "injection_aom_ramper",
            AD9910Ramper,
            "urukul9910_aom_doublepass_689_red_injection",
        )
        self.injection_aom_ramper: AD9910Ramper

        # Fast ramping of the AD9910 controlling the spinpol aom
        self.setattr_fragment(
            "spinpol_aom_ramper",
            AD9910Ramper,
            constants.URUKULED_BEAMS["red_spinpol"].urukul_device,
        )
        self.spinpol_aom_ramper: AD9910Ramper

        # Init of the injection AOM without glitching it if it's already on
        self.setattr_fragment(
            "GlitchFreeUrukulDefaultAttenuation",
            GlitchFreeUrukulDefaultAttenuation,
            "urukul9910_aom_doublepass_689_red_injection",
            constants.URUKULED_BEAMS["red_doublepass_injection"].attenuation,
        )
        self.GlitchFreeUrukulDefaultAttenuation: GlitchFreeUrukulDefaultAttenuation

        # Init of the spin pol AOM without glitching
        self.setattr_fragment(
            "GlitchFreeUrukulSpinPol",
            GlitchFreeUrukulDefaultAttenuation,
            constants.URUKULED_BEAMS["red_spinpol"].urukul_device,
            constants.URUKULED_BEAMS["red_spinpol"].attenuation,
        )

        # Bind

        # Commented out since the cavity EOM is currently driven by a Rigol
        # self.setattr_fragment("laser_stab_system", LaserStabilisationSystem)
        # self.laser_stab_system: LaserStabilisationSystem

        # %% DEVICES

        self.injection_aom: AD9910 = self.get_device(
            "urukul9910_aom_doublepass_689_red_injection"
        )
        self.kernel_invariants.add("injection_aom")

        self.spinpol_aom: AD9910 = self.get_device(
            constants.URUKULED_BEAMS["red_spinpol"].urukul_device
        )
        self.kernel_invariants.add("spinpol_aom")

        self.setattr_device("ttl_shutter_red_axial_mot")
        self.setattr_device("ttl_shutter_red_axial_spin_pol")
        self.ttl_shutter_red_axial_mot: TTLOut
        self.ttl_shutter_red_axial_spin_pol: TTLOut

        # %% PARAMETERS

        self.setattr_param(
            "injection_aom_static_frequency",
            FloatParam,
            "689 injection AOM nominal static frequency",
            unit="MHz",
            min=0,
            default=constants.URUKULED_BEAMS["red_doublepass_injection"].frequency,
        )

        self.setattr_param(
            "spinpol_aom_static_frequency",
            FloatParam,
            "Spin pol AOM nominal static frequency",
            unit="MHz",
            min=0,
            default=constants.URUKULED_BEAMS["red_spinpol"].frequency,
        )

        self.setattr_param(
            "ramp_frequency",
            FloatParam,
            "689 injection AOM ramp frequency",
            unit="kHz",
            min=0,
            default=constants.RED_INJECTION_AOM_RAMP_FREQUENCY,
        )
        self.setattr_param(
            "ramp_lower_detuning",
            FloatParam,
            "Detuning of 689 injection AOM from nominal frequency at lowest point of ramp",
            unit="MHz",
            default=constants.RED_BROADBAND_RAMP_LOWER_LIMIT,
        )
        self.setattr_param(
            "ramp_upper_detuning",
            FloatParam,
            "Detuning of 689 injection AOM from nominal frequency at highest point of ramp",
            unit="MHz",
            default=constants.RED_BROADBAND_RAMP_UPPER_LIMIT,
        )
        self.setattr_param(
            "ramp_type",
            IntParam,
            "689 injection AOM ramp type (0=triangle,1=positive-saw,2=negative-saw)",
            default=2,
        )

        # TODO: These should not be in the beam controller - they're not used for every experiment that uses this object
        self.setattr_param(
            "spinpol_ramp_frequency",
            FloatParam,
            "689 spinpol AOM ramp frequency",
            unit="kHz",
            min=0,
            default=constants.RED_SPINPOL_AOM_RAMP_FREQUENCY,
        )
        self.setattr_param(
            "spinpol_ramp_lower_detuning",
            FloatParam,
            "Detuning of 689 spinpol AOM from nominal frequency at lowest point of ramp",
            unit="MHz",
            default=constants.RED_SPINPOL_RAMP_LOWER_LIMIT,
        )
        self.setattr_param(
            "spinpol_ramp_upper_detuning",
            FloatParam,
            "Detuning of 689 spinpol AOM from nominal frequency at highest point of ramp",
            unit="MHz",
            default=constants.RED_SPINPOL_RAMP_UPPER_LIMIT,
        )
        self.setattr_param(
            "spinpol_ramp_type",
            IntParam,
            "689 spinpol AOM ramp type (0=triangle,1=positive-saw,2=negative-saw)",
            default=0,
        )
        self.setattr_param(
            "use_sigmaplus_spinpol",
            BoolParam,
            "Which spinpol beam? True = sigmaplus, False = sigmaminus",
            default=True,
        )
        self.spinpol_aom_static_frequency: FloatParamHandle
        self.injection_aom_static_frequency: FloatParamHandle
        self.ramp_frequency: FloatParamHandle
        self.ramp_lower_detuning: FloatParamHandle
        self.ramp_upper_detuning: FloatParamHandle
        self.ramp_type: IntParamHandle
        self.spinpol_ramp_frequency: FloatParamHandle
        self.spinpol_ramp_lower_detuning: FloatParamHandle
        self.spinpol_ramp_upper_detuning: FloatParamHandle
        self.spinpol_ramp_type: IntParamHandle
        self.use_sigmaplus_spinpol: BoolParamHandle

        # %% Kernel parameters

        # Initialised here so that it's available across kernels, but calculated
        # in device_setup in case it's varied in a scan
        self.ramp_rate = 0.0
        self.spinpol_ramp_rate = 0.0

        # %% Kernel invariants

        self.debug_mode = logger.isEnabledFor(logging.DEBUG)
        self.kernel_invariants.add("debug_mode")
        self.kernel_invariants.add("injection_aom")

    def host_setup(self):
        super().host_setup()
        assert self.ramp_type.get() in [0, 1, 2], "Ramp type must be 0, 1 or 2"
        assert self.spinpol_ramp_type.get() in [0, 1, 2], "Ramp type must be 0, 1 or 2"
        if self.use_sigmaplus_spinpol.get():
            self.spinpol_toggler = self.sigmaplus_toggler
            self.spinpol_setpoint = constants.RED_SPINPOL_SETPOINT_SIGMAPLUS
            self.spinpol_setter = self.sigmaplus_setpoint_setter
            self.spinpol_reset_setpoint_handle = self.sigmaplus_setpoint_handle

        else:
            self.spinpol_toggler = self.sigmaminus_toggler
            self.spinpol_setpoint = constants.RED_SPINPOL_SETPOINT_SIGMAMINUS
            self.spinpol_setter = self.sigmaminus_setpoint_setter
            self.spinpol_reset_setpoint_handle = self.sigmaminus_setpoint_handle

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

        # Precalculate the spinpol ramp rate required to get the requested modulation frequency
        self.spinpol_ramp_rate = abs(
            (
                self.spinpol_ramp_lower_detuning.get()
                - self.spinpol_ramp_upper_detuning.get()
            )
            * self.spinpol_ramp_frequency.get()
        )

        if self.spinpol_ramp_type.get() == 0:
            # Triangle waves will need to ramp twice as quickly
            self.ramp_rate *= 2

        if self.debug_mode:
            logger.info(
                "Calculated required ramp_rate = %s kHz/s",
                self.spinpol_ramp_rate * 1e-3,
            )

        self.core.break_realtime()

        # Ensure the injection AOM's RF switch is on and the frequency is
        # correct. These are glitch free, so we do them each time
        self.injection_aom.set(self.injection_aom_static_frequency.get())
        self.injection_aom.sw.on()

    @kernel
    def init(self):
        """
        Set up beam state for the red MOT, i.e. set up AOMs and close all shutters

        This is not in device_setup so that the user can choose when / whether to call it during each scan cycle
        """
        # Turn on all the AOMs but close all the shutters
        self.all_beam_default_setter.turn_on_all(light_enabled=False)
        delay_mu(int64(self.core.ref_multiplier))
        self.ttl_shutter_red_axial_mot.off()
        delay_mu(int64(self.core.ref_multiplier))
        self.ttl_shutter_red_axial_spin_pol.off()
        delay_mu(int64(self.core.ref_multiplier))

        # Turn on the spin polarising AOM
        self.spinpol_aom.set(self.spinpol_aom_static_frequency.get())
        self.spinpol_aom.sw.on()

        # Make sure that the shutters are closed before run_once starts
        delay(self.all_beam_default_setter.get_max_shutter_delay())

    @kernel
    def turn_on_mot_beams(self, ignore_shutters=False):
        delay(-constants.SRS_SHUTTER_DELAY)
        self.ttl_shutter_red_axial_mot.on()
        delay(constants.SRS_SHUTTER_DELAY)
        delay_mu(int64(self.core.ref_multiplier))
        self.all_mot_beams_setter.turn_beams_on(ignore_shutters)

    @kernel
    def turn_off_mot_beams(self, ignore_shutters=False):
        self.ttl_shutter_red_axial_mot.off()
        delay_mu(int64(self.core.ref_multiplier))
        self.all_mot_beams_setter.turn_beams_off(ignore_shutters)

    @kernel
    def start_ramping_red(self):
        """
        Start modulation of the 689 DDS as configured

        Advances the timeline by the duration of SPI writes
        """

        self.injection_aom_ramper.start_ramp(
            self.ramp_rate,
            self.injection_aom_static_frequency.get() + self.ramp_lower_detuning.get(),
            self.injection_aom_static_frequency.get() + self.ramp_upper_detuning.get(),
            self.ramp_type.get(),
        )

    @kernel
    def stop_ramping_red(self, freq=0.0):
        """
        Stop modulation of the 689 DDS and return to static (or specified) frequency
        """
        self.injection_aom_ramper.stop_ramp()

        if freq == 0.0:
            self.injection_aom.set(self.injection_aom_static_frequency.get())
        else:
            self.injection_aom.set(freq)

    @kernel
    def start_ramping_spinpol(self):
        """
        Start modulation of the spinpol DDS as configured

        Advances the timeline by the duration of SPI writes
        """

        self.spinpol_aom_ramper.start_ramp(
            self.spinpol_ramp_rate,
            self.spinpol_aom_static_frequency.get()
            + self.spinpol_ramp_lower_detuning.get(),
            self.spinpol_aom_static_frequency.get()
            + self.spinpol_ramp_upper_detuning.get(),
            self.spinpol_ramp_type.get(),
        )

    @kernel
    def stop_ramping_spinpol(self, freq=0.0):
        """
        Stop modulation of the spinpol DDS and return to static (or specified) frequency
        """
        self.spinpol_aom_ramper.stop_ramp()

        if freq == 0.0:
            self.spinpol_aom.set(self.spinpol_aom_static_frequency.get())
        else:
            self.spinpol_aom.set(freq)

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
        freq = self.injection_aom_static_frequency.get() + detuning

        if self.debug_mode:
            logger.info(
                "Setting AOM detuning to %.3f kHz = %.6f MHz on %s",
                detuning * 1e-3,
                freq * 1e-6,
                self.injection_aom,
            )

        self.injection_aom.set(freq)

    @kernel
    def turn_on_spin_pol(self, ignore_shutters=False):
        """
        Turn on the selected spin polarization beam

        Note that this will use the appropriate AOM for suservoing, and
        therefore cannot be used while the 9/2 -> 11/2 MOT beams are on. You
        must ensure that they are not, otherwise it'll be weird.
        """
        # Ensure shutter is open
        delay(-constants.SRS_SHUTTER_DELAY)
        self.ttl_shutter_red_axial_spin_pol.on()
        delay(constants.SRS_SHUTTER_DELAY)

        # Update the appropriate SUServo with the new setpoint and turn it on
        self.spinpol_setter.set_setpoint(self.spinpol_setpoint)
        self.spinpol_setter.set_pgia_gain_mu(constants.RED_SPINPOL_PGIA_GAIN)
        self.spinpol_setter.set_iir_params()  # Use default IIR params
        self.spinpol_toggler.turn_beams_on(ignore_shutters)

    @kernel
    def turn_off_spin_pol(self, ignore_shutters=False):
        # Turn off the spin pol beam and reset the setpoint back to normal
        self.ttl_shutter_red_axial_spin_pol.off()
        delay_mu(int64(self.core.ref_multiplier))
        self.spinpol_setter.set_setpoint(self.spinpol_reset_setpoint_handle.get())
        delay_mu(int64(self.core.ref_multiplier))
        self.spinpol_toggler.turn_beams_off(ignore_shutters)
