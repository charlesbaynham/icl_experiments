import logging

from artiq.language import kernel
from ndscan.experiment import Fragment
from ndscan.experiment.parameters import BoolParam
from ndscan.experiment.parameters import BoolParamHandle
from pyaion.fragments.default_beam_setter import SetBeamsToDefaults
from pyaion.fragments.default_beam_setter import make_set_beams_to_default

from repository.lib import constants
from repository.lib.experiment_templates.red_mot_experiment import (
    RedMOTWithExperimentBase,
)

logger = logging.getLogger(__name__)


class ConstantBeamsMixin(RedMOTWithExperimentBase):
    """
    Leaves a list of SUServo beams on throughout the entire sequence.

    Current list:
    * squeezing_cavity_698

    Set the ``ConstantBeamsEnabled`` parameter to False to disable the mixin:
    the beams are then left untouched (not turned on) and the mixin does
    nothing.

    This is a mixin - see the documentation for :mod:`~.red_mot_experiment` for
    details.

    Kernel hooks used (multiple mixins cannot use the same hooks):

    * None
    """

    def build_fragment(self):
        super().build_fragment()

        class ConstantBeamsInDeviceSetup(Fragment):
            def build_fragment(self):
                self.setattr_device("core")

                # %% Fragments
                self.setattr_fragment(
                    "constant_dipole_traps_setter",
                    make_set_beams_to_default(
                        suservo_beam_infos=[
                            constants.SUSERVOED_BEAMS["lattice_input_1379"],
                            constants.SUSERVOED_BEAMS["down_813"],
                            # constants.SUSERVOED_BEAMS["up_813"],
                            constants.SUSERVOED_BEAMS["dipole_trap_1064_delivery"],
                            # constants.SUSERVOED_BEAMS["dipole_trap_painted_1064_delivery"],
                            # constants.SUSERVOED_BEAMS["clock_delivery"],
                            # constants.SUSERVOED_BEAMS["stark_shifter_689_delivery"],
                            constants.SUSERVOED_BEAMS["squeezing_cavity_698"],
                        ],
                        urukul_beam_infos=[
                            # constants.URUKULED_BEAMS["clock_up"],
                        ],
                        name="constant_dipole_traps_setter",
                        use_automatic_setup=False,
                        use_automatic_turnon=False,
                    ),
                )
                self.constant_dipole_traps_setter: SetBeamsToDefaults

                self.setattr_param(
                    "ConstantBeamsEnabled",
                    BoolParam,
                    default=True,
                    description="Leave the constant beams on throughout the "
                    "sequence. If False, this mixin does nothing.",
                )
                self.ConstantBeamsEnabled: BoolParamHandle

            @kernel
            def device_setup(self):
                self.device_setup_subfragments()

                if self.ConstantBeamsEnabled.get():
                    self.core.break_realtime()
                    self.constant_dipole_traps_setter.turn_on_all(light_enabled=True)

        self.setattr_fragment(
            "constant_beams_in_device_setup", ConstantBeamsInDeviceSetup
        )
        self.constant_beams_in_device_setup: ConstantBeamsInDeviceSetup
