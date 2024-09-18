import logging

from artiq.coredevice.ad9910 import AD9910
from artiq.coredevice.ttl import TTLOut
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
from repository.lib.experiment_templates.red_mot_experiment import (
    RedMOTWithExperiment,
)


logger = logging.getLogger(__name__)


class DipoleTrapMixin(RedMOTWithExperiment):
    """
    Loads atoms into a dipole trap before spectroscopy

    This mixin load atoms into a dipole trap at the end of the narrowband red MOT.
    The "expansion time" begins from the end of the
    dipole trap.

    This is a mixin - see the documentation for :mod:`~.red_mot_experiment` for
    details.

    Kernel hooks used (multiple mixins cannot use the same hooks):

    * :meth:`~post_narrowband_hook`
    * :meth:`~set_fields_hook`
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

        self.setattr_param(
            "dipole_trap_molasses_duration",
            FloatParam,
            "Time to run rMOT beams in molasses mode",
            default=constants.DIPOLE_TRAP_MOLASSES_DURATION,
            min=0,
            unit="ms",
        )
        self.dipole_trap_molasses_duration: FloatParamHandle

        self.setattr_param(
            "dipole_trap_molasses_detuning",
            FloatParam,
            "Detuning for rMOT beams in molasses mode",
            default=constants.DIPOLE_TRAP_MOLASSES_DETUNING,
            unit="kHz",
        )
        self.dipole_trap_molasses_detuning: FloatParamHandle

        self.setattr_param(
            "dipole_trap_molasses_suservo_multiple",
            FloatParam,
            "SUServo multiple for rMOT beams in molasses mode",
            default=constants.DIPOLE_TRAP_MOLASSES_SETPOINT_MULTIPLE,
        )
        self.dipole_trap_molasses_suservo_multiple: FloatParamHandle

        # %% Fragments

        self.setattr_fragment(
            "dipole_trap_setter",
            make_set_beams_to_default(
                suservo_beam_infos=[
                    constants.SUSERVOED_BEAMS["dipole_trap_1064_delivery"]
                ],
                urukul_beam_infos=[
                    constants.URUKULED_BEAMS["dipole_trap_1064_switch"],
                ],
                use_automatic_setup=True,
                name="dipole_trap_setter",
            ),
        )
        self.dipole_trap_setter: SetBeamsToDefaults

    def host_setup(self):
        self.dipole_switch_urukul: AD9910 = self.get_device(
            constants.URUKULED_BEAMS["dipole_trap_1064_switch"].urukul_device
        )

        if not hasattr(self.dipole_switch_urukul, "sw"):
            raise TypeError(
                "This mixin assumes that the 1064 switch AOM is controlled by an Urukul channel with a dedicated TTL for the RF switch"
            )

        self.dipole_switch_ttl: TTLOut = self.dipole_switch_urukul.sw

        self.kernel_invariants = getattr(self, "kernel_invariants", set())
        self.kernel_invariants.add("dipole_delivery_sw")

        return super().host_setup()

    @kernel
    def post_narrowband_hook(self):
        self.post_narrowband_hook_dipole_trap()

    @kernel
    def set_fields_hook(self):
        """
        Prevent field setting in the normal place: we'll do it at the start of
        the dipole trap instead
        """
        pass

    @kernel
    def post_narrowband_hook_dipole_trap(self):
        """
        Load into the dipole trap while the red MOT is still on and then hold it
        for the configured time before dropping the atoms.
        """
        load_time_mu = self.core.seconds_to_mu(self.dipole_trap_load_time.get())

        delay_mu(-load_time_mu)
        self.dipole_switch_ttl.on()
        delay_mu(load_time_mu)

        # Set the spectroscopy field gradient at the start of the dipole trap
        # (after the "loading" phase)
        self.set_fields_default()

        # If configured, add a molasses stage
        molasses_time = self.dipole_trap_molasses_duration.get()
        if molasses_time > 0.0:
            self.red_mot.red_beam_controller.set_mot_detuning(
                self.dipole_trap_molasses_detuning.get()
            )
            suservo_multiple = self.dipole_trap_molasses_suservo_multiple.get()
            self.red_mot.red_beam_controller.set_mot_suservo_amplitudes(
                suservo_multiple, suservo_multiple, suservo_multiple, suservo_multiple
            )
            delay(self.dipole_trap_molasses_duration.get())

        self.red_mot.red_beam_controller.turn_off_mot_beams(ignore_shutters=True)

        delay(self.dipole_trap_hold_time.get())

        self.dipole_switch_ttl.off()
