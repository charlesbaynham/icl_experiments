from artiq.language import delay
from artiq.language import kernel
from ndscan.experiment.parameters import FloatParam
from ndscan.experiment.parameters import FloatParamHandle
from pyaion.fragments.suservo import LibSetSUServoStatic

import repository.lib.constants as constants
from repository.lib.experiment_templates.dipole_trap_experiment import (
    DipoleTrapWithExperiment,
)


class SwitchHODT(DipoleTrapWithExperiment):
    """
    Switch the 1064 power back up after the evaporation stage.

    Kernel hooks used (multiple mixins cannot use the same hooks):

    * :meth:`~do_experiment_after_dipole_trap_hook`
    """

    def build_fragment(self):
        super().build_fragment()

        self.setattr_fragment(
            "hodt_suservo",
            LibSetSUServoStatic,
            constants.SUSERVOED_BEAMS["dipole_trap_1064_delivery"].suservo_device,
        )
        self.hodt_suservo: LibSetSUServoStatic

        self.setattr_fragment(
            "vodt_suservo",
            LibSetSUServoStatic,
            constants.SUSERVOED_BEAMS["down_813"].suservo_device,
        )
        self.vodt_suservo: LibSetSUServoStatic

        self.setattr_param(
            "slosh_time",
            FloatParam,
            "Time to slosh the atoms for",
            default=50e-6,
            unit="us",
        )

        self.slosh_time: FloatParamHandle

        self.setattr_param(
            "setpoint_hodt",
            FloatParam,
            "Setpoint for HODT SUServo during slosh",
            default=4.7,
            unit="V",
        )

        self.setpoint_hodt: FloatParamHandle

    @kernel
    def post_dipole_trap_hook(self):
        """
        keep dipole beams on after evap
        """

    @kernel
    def do_experiment_after_dipole_trap_hook(self):
        self.hodt_suservo.set_setpoint(self.setpoint_hodt.get())
        self.hodt_suservo.set_suservo(
            freq=110e6,
            amplitude=1.0,
            attenuation=2.0,
            setpoint_v=self.setpoint_hodt.get(),
            enable_iir=True,
        )
        delay(self.slosh_time.get())
        self.hodt_suservo.set_channel_state(rf_switch_state=False, enable_iir=False)
        self.vodt_suservo.set_channel_state(rf_switch_state=False, enable_iir=False)
