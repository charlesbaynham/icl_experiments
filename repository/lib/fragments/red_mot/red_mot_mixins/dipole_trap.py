import logging

from artiq.experiment import delay
from artiq.experiment import delay_mu
from artiq.experiment import kernel
from ndscan.experiment.parameters import FloatParam
from ndscan.experiment.parameters import FloatParamHandle
from numpy import int64
from pyaion.fragments.default_beam_setter import make_set_beams_to_default
from pyaion.fragments.default_beam_setter import SetBeamsToDefaults
from pyaion.fragments.suservo import LibSetSUServoStatic

from repository.lib import constants
from repository.lib.fragments.red_mot.red_mot_experiment import (
    RedMOTWithExperiment,
)


logger = logging.getLogger(__name__)


# FIXME This is not finished
class DipoleTrapMixin(RedMOTWithExperiment):
    """
    Loads atoms into a dipole trap before spectroscopy

    This mixin load atoms into a dipole trap at the end of the narrowband red MOT.
    The "expansion time" begins from the end of the
    dipole trap.

    This is a mixin - see the documentation for :mod:`~.red_mot_experiment` for
    details.

    Kernel hooks used (multiple mixins cannot use the same hooks):

    * :meth:`~before_start_hook`
    * :meth:`~post_narrowband_hook`
    """

    def build_fragment(self):
        super().build_fragment()

        self.setattr_param(
            "dipole_trap_hold_time",
            FloatParam,
            "Time to hold in dipole trap",
            default=constants.DIPOLE_TRAP_HOLD_TIME,
            unit="ms",
        )
        self.dipole_trap_hold_time: FloatParamHandle

        self.setattr_param(
            "dipole_trap_load_time",
            FloatParam,
            "Time to enable dipole trap before MOT ends",
            default=constants.DIPOLE_TRAP_LOADING_TIME,
            unit="ms",
        )
        self.dipole_trap_load_time: FloatParamHandle

        # %% Fragments

        self.setattr_fragment(
            "lattice_suservo",
            LibSetSUServoStatic,
            constants.SUSERVOED_BEAMS["lattice_input_1379"].suservo_device,
        )
        self.lattice_suservo: LibSetSUServoStatic

        self.setattr_fragment(
            "dipole_trap_setter",
            make_set_beams_to_default(
                urukul_beam_infos=[
                    constants.URUKULED_BEAMS["dipole_trap_1064_delivery"],
                    constants.URUKULED_BEAMS["dipole_trap_1064_switch"],
                ]
            ),
        )
        self.dipole_trap_setter: SetBeamsToDefaults

    @kernel
    def device_setup(self) -> None:
        self.core.break_realtime()
        self.dipole_trap_setter.turn_on_all(light_enabled=False)

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
        self.red_mot.red_beam_controller.turn_on_spin_pol(ignore_shutters=True)
        delay(self.duration_spinpol_pulse.get())
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

        # After the sequence completes, put the lattice back to its high setpoint
        self.lattice_suservo.set_setpoint(self.lattice_high_setpoint.get())
