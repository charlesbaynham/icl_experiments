import logging

from artiq.experiment import delay
from artiq.experiment import delay_mu
from artiq.experiment import kernel
from ndscan.experiment.parameters import FloatParam
from ndscan.experiment.parameters import FloatParamHandle
from pyaion.fragments.default_beam_setter import SetBeamsToDefaults
from pyaion.fragments.default_beam_setter import make_set_beams_to_default

from repository.lib import constants
from repository.lib.experiment_templates.red_mot_experiment import RedMOTWithExperiment
from repository.lib.fragments.pyaion_overrides.suservo_override import (
    LibSetSUServoStatic,
)
from repository.lib.fragments.ramping_phase_bound import (
    GeneralRampingPhaseWithBindingAndBiasField,
)

logger = logging.getLogger(__name__)


class FieldAndLatticeRampingPhase(GeneralRampingPhaseWithBindingAndBiasField):
    """
    A ramping phase with ramps for 1379 nm lattice and bias fields

    We only define a single set of ramp parameters (unlike in the red MOT ramping phases) because we will probably only use this phase on Sr87

    The default suservo "nominal" is set to zero: It must be a bound to other parameters or values after this phase is instantiated or added as a subfragment
    """

    duration_default = 100e-3
    time_step_default = 1e-3

    suservos = ["suservo_aom_singlepass_1379_cavity_input"]

    # These must be overridden / rebound by consumer fragments otherwise not
    # much will happen. This is done so that all the phases can share the same
    # detuning / nominal setpoints. Use
    # self.bind_suservo_setpoint_params_to_default_beam_setter for this.
    default_suservo_nominal_setpoints = [0.0]
    default_suservo_setpoint_multiples_start = 1.0
    default_suservo_setpoint_multiples_end = 1.0

    # Chamber 2 bias coils in amps [X, Y, Z]
    general_setter_default_starts = constants.FIELD_COMP
    general_setter_default_ends = constants.FIELD_COMP


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

        self.setattr_fragment(
            "field_and_lattice_ramp",
            FieldAndLatticeRampingPhase,
        )
        self.field_and_lattice_ramp: FieldAndLatticeRampingPhase

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

        self.field_and_lattice_ramp.bind_suservo_setpoint_params_to_default_beam_setter(
            self.lattice_setter
        )

        # FIXME This needs to have a different multiplier for the lattice setpoint. Could just ues the default setpoint for this.
        self.field_and_lattice_ramp.bind_param(
            "setpoint_multiple_start_suservo_aom_singlepass_1379_cavity_input",
            self.lattice_high_setpoint,
        )

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
