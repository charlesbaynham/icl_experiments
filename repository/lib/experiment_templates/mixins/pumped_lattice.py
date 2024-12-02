import logging
from typing import List

from artiq.coredevice.ad9910 import AD9910
from artiq.coredevice.core import Core
from artiq.coredevice.ttl import TTLOut
from artiq.experiment import TFloat
from artiq.experiment import delay
from artiq.experiment import delay_mu
from artiq.experiment import kernel
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

import logging

from artiq.experiment import delay
from artiq.experiment import delay_mu
from artiq.experiment import kernel
from ndscan.experiment.parameters import (
    FloatParam,
    IntParam,
    BoolParam,
    BoolParamHandle,
    IntParamHandle,
)
from ndscan.experiment.parameters import FloatParamHandle
from pyaion.fragments.default_beam_setter import SetBeamsToDefaults
from pyaion.fragments.default_beam_setter import make_set_beams_to_default
from pyaion.fragments.suservo import LibSetSUServoStatic

from repository.lib import constants
from repository.lib.experiment_templates.red_mot_experiment import RedMOTWithExperiment

logger = logging.getLogger(__name__)


class OpticalPumpingBase(RedMOTWithExperiment):
    """
    Defines :meth:`~spin_polarize` and :meth:`~.set_fields_for_optical_pumping`
    methods for use in optical pumping Mixins

    Although implemented as a mixin, this is a Fragment at heart and may be
    redefined as one later.
    """

    def build_fragment(self):
        super().build_fragment()

        ## Parameters

        self.setattr_param(
            "delay_before_spinpol_pulse",
            FloatParam,
            "Time in lattice before the spin polarization pulse",
            default=constants.DELAY_BEFORE_OPTICAL_PUMPING,
            unit="ms",
        )
        self.delay_before_spinpol_pulse: FloatParamHandle

        self.setattr_param(
            "duration_spinpol_pulse",
            FloatParam,
            "Duration of the spin polarizing pulse",
            default=constants.DURATION_OF_SPIN_POL,
            unit="ms",
        )
        self.duration_spinpol_pulse: FloatParamHandle

        self.setattr_param(
            "delay_after_spinpol_pulse",
            FloatParam,
            "Time in lattice after the spin polarization pulse",
            default=constants.DELAY_AFTER_OPTICAL_PUMPING,
            unit="ms",
        )
        self.delay_after_spinpol_pulse: FloatParamHandle

        self.setattr_param(
            "spinpol_aom_static_frequency",
            FloatParam,
            "Spin pol AOM nominal static frequency",
            unit="MHz",
            default=constants.URUKULED_BEAMS["red_spinpol"].frequency,
        )
        self.setattr_param(
            "spinpol_ramp_frequency",
            FloatParam,
            "689 spinpol AOM ramp frequency",
            unit="kHz",
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
        self.spinpol_ramp_frequency: FloatParamHandle
        self.spinpol_ramp_lower_detuning: FloatParamHandle
        self.spinpol_ramp_upper_detuning: FloatParamHandle
        self.spinpol_ramp_type: IntParamHandle
        self.use_sigmaplus_spinpol: BoolParamHandle

        for idx, c in enumerate("xyz"):
            self.setattr_param(
                f"bias_{c}_for_pumping",
                FloatParam,
                default=constants.OPTICAL_PUMPING_BIAS_FIELD[idx],
                description=f"Bias field for optical pumping {c}",
                unit="A",
            )
        self.bias_x_for_pumping: FloatParamHandle
        self.bias_y_for_pumping: FloatParamHandle
        self.bias_z_for_pumping: FloatParamHandle

        ## Fragments

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

        # Fast ramping of the AD9910 controlling the spinpol aom
        self.setattr_fragment(
            "spinpol_aom_ramper",
            AD9910Ramper,
            constants.URUKULED_BEAMS["red_spinpol"].urukul_device,
        )
        self.spinpol_aom_ramper: AD9910Ramper

        # Init of the spin pol AOM without glitching
        # FIXME doesn't need to be glitchfree
        self.setattr_fragment(
            "GlitchFreeUrukulSpinPol",
            GlitchFreeUrukulDefaultAttenuation,
            constants.URUKULED_BEAMS["red_spinpol"].urukul_device,
            constants.URUKULED_BEAMS["red_spinpol"].attenuation,
        )

        ## Devices

        self.spinpol_aom: AD9910 = self.get_device(
            constants.URUKULED_BEAMS["red_spinpol"].urukul_device
        )
        self.kernel_invariants.add("spinpol_aom")

        self.setattr_device("ttl_shutter_red_axial_spin_pol")
        self.ttl_shutter_red_axial_spin_pol: TTLOut

        # Params

        self.spinpol_ramp_rate = 0.0

    def host_setup(self):
        super().host_setup()

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
    def spin_polarize(self):
        """
        Spin polarize the atoms trapped in the lattice by pulsing the selected
        beam after allowing the atoms to equlibriate in the lattice for a time,
        then hold them afterwards for some time.
        """
        self.red_mot.red_beam_controller.turn_off_mot_beams(ignore_shutters=True)
        delay(self.delay_before_spinpol_pulse.get())
        self.red_mot.red_beam_controller.turn_on_spin_pol(ignore_shutters=True)
        delay(self.duration_spinpol_pulse.get())
        self.red_mot.red_beam_controller.turn_off_spin_pol(ignore_shutters=False)
        delay(self.delay_after_spinpol_pulse.get())

    @kernel
    def set_fields_for_optical_pumping(self):
        """
        Set the bias fields for optical pumping

        Advances the timeline by 5 us to avoid RTIO clashes with previous phase
        """
        # Delay to avoid RTIO clashes with previous phase: set
        # fields writes into past
        delay(5e-6)
        self.red_mot.chamber_2_field_setter.set_all_fields(
            0.0,
            self.bias_x_for_pumping.get(),
            self.bias_y_for_pumping.get(),
            self.bias_z_for_pumping.get(),
        )

    # FIXME this must go somewhere
    # # Precalculate the spinpol ramp rate required to get the requested modulation frequency
    #     self.spinpol_ramp_rate = abs(
    #         (
    #             self.spinpol_ramp_lower_detuning.get()
    #             - self.spinpol_ramp_upper_detuning.get()
    #         )
    #         * self.spinpol_ramp_frequency.get()
    #     )

    #     if self.spinpol_ramp_type.get() == 0:
    #         # Triangle waves will need to ramp twice as quickly
    #         self.ramp_rate *= 2

    #     if self.debug_mode:
    #         logger.info(
    #             "Calculated required ramp_rate = %s kHz/s",
    #             self.spinpol_ramp_rate * 1e-3,
    #         )

    # self.ttl_shutter_red_axial_spin_pol.off()
    #     delay_mu(int64(self.core.ref_multiplier))

    #     # Turn on the spin polarising AOM
    #     self.spinpol_aom.set(self.spinpol_aom_static_frequency.get())
    #     self.spinpol_aom.sw.on()

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
        self.spinpol_toggler.turn_beams_on(ignore_shutters)

    @kernel
    def turn_off_spin_pol(self, ignore_shutters=False):
        # Turn off the spin pol beam and reset the setpoint back to normal
        self.ttl_shutter_red_axial_spin_pol.off()
        delay_mu(int64(self.core.ref_multiplier))
        self.spinpol_setter.set_setpoint(self.spinpol_reset_setpoint_handle.get())
        delay_mu(int64(self.core.ref_multiplier))
        self.spinpol_toggler.turn_beams_off(ignore_shutters)


class OpticalPumpingWithFieldSettingDipoleTrapMixin(OpticalPumpingBase):
    """
    Mixin for optical pumping in a dipole trap

    Kernel hooks used (multiple mixins cannot use the same hooks):

    * :meth:`~dipole_trap_optical_pumping_hook`
    """

    @kernel
    def dipole_trap_optical_pumping_hook(self):
        self.set_fields_for_optical_pumping()
        self.spin_polarize()


# TODO: Refactor DroppedPumpedLatticeMixin to use Base classes above
# Note: fields aren't set in this Mixin, so it only works with FieldBoostMixin
class DroppedPumpedLatticeMixin(RedMOTWithExperiment):
    """
    Loads atoms into a lattice, pumps them into a stretched state then drops
    them by quickly ramping down the lattice intensity

    This mixin load atoms into a lattice at the end of the narrowband red MOT,
    pumping them using the spin polarisation beam then dropping them by ramping
    down the lattice intensity. The "expansion time" begins from the end of the
    ramp down.

    This is a mixin - see the documentation for :mod:`~.red_mot_experiment` for
    details.

    Kernel hooks used (multiple mixins cannot use the same hooks):

    * :meth:`~before_start_hook`
    * :meth:`~post_narrowband_hook`
    * :meth:`~post_sequence_cleanup_hook`
    """

    def build_fragment(self):
        super().build_fragment()

        self.setattr_param(
            "delay_before_spinpol_pulse",
            FloatParam,
            "Time in lattice before the spin polarization pulse",
            default=constants.DELAY_BEFORE_OPTICAL_PUMPING,
            unit="ms",
        )
        self.delay_before_spinpol_pulse: FloatParamHandle

        self.setattr_param(
            "duration_spinpol_pulse",
            FloatParam,
            "Duration of the spin polarizing pulse",
            default=constants.DURATION_OF_SPIN_POL,
            unit="ms",
        )
        self.duration_spinpol_pulse: FloatParamHandle

        self.setattr_param(
            "delay_after_spinpol_pulse",
            FloatParam,
            "Time in lattice after the spin polarization pulse",
            default=constants.DELAY_AFTER_OPTICAL_PUMPING,
            unit="ms",
        )
        self.delay_after_spinpol_pulse: FloatParamHandle

        self.setattr_param(
            "lattice_high_setpoint",
            FloatParam,
            "SUServo setpoint for lattice at high power",
            default=constants.LATTICE_HIGH_SETPOINT_MULTIPLE
            * constants.SUSERVOED_BEAMS["lattice_input_1379"].setpoint,
            unit="V",
        )
        self.lattice_high_setpoint: FloatParamHandle

        self.setattr_param(
            "lattice_low_setpoint",
            FloatParam,
            "SUServo setpoint for lattice at low power",
            default=constants.LATTICE_LOW_SETPOINT_MULTIPLE
            * constants.SUSERVOED_BEAMS["lattice_input_1379"].setpoint,
            unit="V",
        )
        self.lattice_low_setpoint: FloatParamHandle

        # %% Fragments

        self.setattr_fragment(
            "lattice_suservo",
            LibSetSUServoStatic,
            constants.SUSERVOED_BEAMS["lattice_input_1379"].suservo_device,
        )
        self.lattice_suservo: LibSetSUServoStatic

        self.setattr_fragment(
            "lattice_setter",
            make_set_beams_to_default(
                suservo_beam_infos=[constants.SUSERVOED_BEAMS["lattice_input_1379"]]
            ),
        )
        self.lattice_setter: SetBeamsToDefaults

    @kernel
    def device_setup(self) -> None:
        self.core.break_realtime()
        self.lattice_setter.turn_on_all()

        self.device_setup_subfragments()

    @kernel
    def post_narrowband_hook(self):
        self.load_into_lattice()
        self.spin_polarize()
        self.ramp_down_lattice()

    @kernel
    def load_into_lattice(self):
        """
        Load into the lattice with a bang - no ramping for now. Don't do the
        shutter wiggle thing, since that would clash with the spin pol pulse
        we're about to do
        """
        self.lattice_suservo.set_setpoint(self.lattice_high_setpoint.get())
        self.red_mot.red_beam_controller.turn_off_mot_beams(ignore_shutters=True)

    @kernel
    def spin_polarize(self):
        """
        Spin polarize the atoms trapped in the lattice by pulsing the selected
        beam after allowing the atoms to equlibriate in the lattice for a time,
        then hold them afterwards for some time.
        """
        delay(self.delay_before_spinpol_pulse.get())
        self.red_mot.red_beam_controller.start_ramping_spinpol()
        delay_mu(8)
        self.red_mot.red_beam_controller.turn_on_spin_pol(ignore_shutters=True)
        delay(self.duration_spinpol_pulse.get())
        self.red_mot.red_beam_controller.stop_ramping_spinpol()
        delay_mu(8)
        self.red_mot.red_beam_controller.turn_off_spin_pol(ignore_shutters=False)
        delay(self.delay_after_spinpol_pulse.get())

    @kernel
    def ramp_down_lattice(self):
        """
        For now, just drop the lattice setpoint immediately.

        We could implement a ramp later if it turns out to be required, or we
        could (temporarily) reduce the gain on the SUServo loop to effectivly
        low-pass filter this step
        """
        self.lattice_suservo.set_setpoint(self.lattice_low_setpoint.get())

    @kernel
    def post_sequence_cleanup_hook(self):
        self.post_sequence_cleanup_hook_base()
        self.post_sequence_cleanup_hook_lattice()

    @kernel
    def post_sequence_cleanup_hook_lattice(self):
        # After the sequence completes, put the lattice back to its high setpoint
        self.lattice_suservo.set_setpoint(self.lattice_high_setpoint.get())
