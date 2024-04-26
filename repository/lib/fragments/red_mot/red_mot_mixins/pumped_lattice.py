import logging

from artiq.experiment import delay
from artiq.experiment import delay_mu
from artiq.experiment import kernel
from ndscan.experiment.parameters import FloatParam
from ndscan.experiment.parameters import FloatParamHandle
from numpy import int64
from pyaion.fragments.suservo import LibSetSUServoStatic

from repository.lib import constants
from repository.lib.fragments.red_mot.red_mot_experiment import (
    RedMOTWithExperiment,
)


logger = logging.getLogger(__name__)


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

    * :meth:`~post_narrowband_hook`
    """

    def build_fragment(self):
        super().build_fragment()

        self.setattr_param(
            "delay_before_spinpol_pulse",
            FloatParam,
            "Time in lattice before the spin polarization pulse",
            default=constants.TIME_IN_LATTICE_BEFORE_SPIN_POL,
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
            default=constants.TIME_IN_LATTICE_AFTER_SPIN_POL,
            unit="ms",
        )
        self.delay_after_spinpol_pulse: FloatParamHandle

        self.setattr_param(
            "lattice_high_setpoint",
            FloatParam,
            "SUServo setpoint for lattice at high power",
            default=constants.LATTICE_HIGH_SETPOINT,
            unit="V",
        )
        self.lattice_high_setpoint: FloatParamHandle

        self.setattr_param(
            "lattice_low_setpoint",
            FloatParam,
            "SUServo setpoint for lattice at low power",
            default=constants.LATTICE_LOW_SETPOINT,
            unit="V",
        )
        self.lattice_low_setpoint: FloatParamHandle

        # %% Fragments

        self.setattr_fragment(
            "lattice_suservo",
            LibSetSUServoStatic,
            "suservo_aom_singlepass_1379_cavity_input",
        )
        self.lattice_suservo: LibSetSUServoStatic

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
        # The MOT beams are already off, but this closes the SUServo shutters
        # and warms the AOMs back up
        delay_mu(int64(self.core.ref_multiplier))
        self.red_mot.red_beam_controller.turn_off_mot_beams(ignore_shutters=False)
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
