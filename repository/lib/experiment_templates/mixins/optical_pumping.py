import logging

from artiq.language import delay
from artiq.language import delay_mu
from artiq.language import kernel
from ndscan.experiment.parameters import FloatParam
from ndscan.experiment.parameters import FloatParamHandle
from pyaion.fragments.default_beam_setter import SetBeamsToDefaults
from pyaion.fragments.default_beam_setter import make_set_beams_to_default
from pyaion.fragments.suservo import LibSetSUServoStatic

from repository.lib import constants
from repository.lib.experiment_templates.dipole_trap_experiment import (
    DipoleTrapWithExperiment,
)
from repository.lib.experiment_templates.red_mot_experiment import RedMOTWithExperiment

logger = logging.getLogger(__name__)


class OpticalPumpingBase(RedMOTWithExperiment):
    """
    Defines a spin_polarize() method for use in optical pumping Mixins
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

    def get_always_shown_params(self):
        # Don't show params
        param_handles = super().get_always_shown_params()
        param_handles.remove(self.delay_before_spinpol_pulse)
        param_handles.remove(self.delay_after_spinpol_pulse)
        return param_handles

    @kernel
    def spin_polarize(self):
        """
        Spin polarize the atoms trapped in the lattice by pulsing the selected
        beam after allowing the atoms to equlibriate in the lattice for a time,
        then hold them afterwards for some time.
        """
        self.red_mot.red_beam_controller.start_ramping_spinpol()
        self.red_mot.red_beam_controller.turn_off_mot_beams(ignore_shutters=True)
        delay(self.delay_before_spinpol_pulse.get())
        self.red_mot.red_beam_controller.turn_on_spin_pol(ignore_shutters=True)
        delay(self.duration_spinpol_pulse.get())
        self.red_mot.red_beam_controller.stop_ramping_spinpol()
        self.red_mot.red_beam_controller.turn_off_spin_pol(ignore_shutters=False)
        delay(self.delay_after_spinpol_pulse.get())


class OpticalPumpingWithFieldSettingBase(OpticalPumpingBase):
    """
    Exposes spin_polarize() and set_fields_for_optical_pumping() methods
    for use in optical pumping Mixins
    """

    def build_fragment(self):
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

        super().build_fragment()

    def get_always_shown_params(self):
        # Don't show params
        param_handles = super().get_always_shown_params()
        param_handles.remove(self.bias_x_for_pumping)
        param_handles.remove(self.bias_y_for_pumping)
        param_handles.remove(self.bias_z_for_pumping)
        return param_handles

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


class OpticalPumpingWithFieldSettingDipoleTrapMixin(
    OpticalPumpingWithFieldSettingBase, DipoleTrapWithExperiment
):
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
        # TODO: This won't work, it overrides the device_setup in
        # red_mot_experiment, clashing with all the other mixins
        raise RuntimeError
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
