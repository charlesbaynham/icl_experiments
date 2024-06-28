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
from repository.lib.fragments.red_mot.red_mot_experiment import (
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

        self.dipole_delivery_urukul: AD9910 = self.get_device(
            constants.URUKULED_BEAMS["dipole_trap_1064_switch"].urukul_device
        )

        if not hasattr(self.dipole_delivery_urukul, "sw"):
            raise TypeError(
                "This mixin assumes that the 1064 delivery AOM is controlled by an Urukul channel with a dedicated TTL for the RF switch"
            )

        self.dipole_delivery_sw: TTLOut = self.dipole_delivery_urukul.sw

        self.kernel_invariants = getattr(self, "kernel_invariants", set())
        self.kernel_invariants.add("dipole_delivery_sw")

        self.setattr_fragment(
            "dipole_trap_setter",
            make_set_beams_to_default(
                urukul_beam_infos=[
                    constants.URUKULED_BEAMS[
                        "dipole_trap_1064_delivery"
                    ],  # FIXME: the dipole trap delivery needs to be on a SUServo and needs to be enabled throughout
                    constants.URUKULED_BEAMS["dipole_trap_1064_switch"],
                ],
                automatic_setup=True,
                name="dipole_trap_setter",
            ),
        )
        self.dipole_trap_setter: SetBeamsToDefaults

    @kernel
    def post_narrowband_hook(self):
        self.post_narrowband_hook_dipole_trap()

    @kernel
    def post_narrowband_hook_dipole_trap(self):
        """
        Load into the dipole trap while the red MOT is still on and then hold it
        for the configured time before dropping the atoms.
        """
        load_time_mu = self.core.seconds_to_mu(self.dipole_trap_load_time.get())

        delay_mu(-load_time_mu)
        self.dipole_delivery_sw.on()
        delay_mu(load_time_mu)
        self.red_mot.red_beam_controller.turn_off_mot_beams(ignore_shutters=True)
        delay(self.dipole_trap_hold_time.get())
        self.dipole_delivery_sw.off()
