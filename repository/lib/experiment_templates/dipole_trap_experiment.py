import abc
import logging

from artiq.experiment import delay
from artiq.experiment import kernel
from ndscan.experiment.parameters import FloatParam
from ndscan.experiment.parameters import FloatParamHandle
from pyaion.fragments.default_beam_setter import SetBeamsToDefaults
from pyaion.fragments.default_beam_setter import make_set_beams_to_default

from repository.lib import constants
from repository.lib.experiment_templates.red_mot_experiment import RedMOTWithExperiment
from repository.lib.fragments.dipole_trap.dipole_trap_beam_controller import (
    DipoleBeamController,
)

logger = logging.getLogger(__name__)


class DipoleTrapWithExperiment(RedMOTWithExperiment):
    """
    Adaptation of :class:`~repository.lib.experiment_templates.red_mot_experiment.RedMOTWithExperiment` for use with dipole traps. See
    the documentation of :class:`~repository.lib.experiment_templates.red_mot_experiment.RedMOTWithExperiment` for full details.

    This base class removes :meth:`do_experiment_after_red_mot_hook`, replacing
    it with extra hooks:

    * :meth:`dipole_trap_molasses_hook`
    * :meth:`dipole_trap_optical_pumping_hook`
    * :meth:`dipole_trap_evaporation_hook`
    * :meth:`post_dipole_trap_hook`
    * :meth:`do_experiment_after_dipole_trap_hook`
    """

    def build_fragment(self):
        super().build_fragment()

        self.setattr_fragment("dipole_beam_controller", DipoleBeamController)
        self.dipole_beam_controller: DipoleBeamController

        # Hold time in dipole trap - can be negative
        self.setattr_param(
            "dipole_hold_time",
            FloatParam,
            "Time to hold final dipole trap before experiment",
            default=0.0,
            unit="us",
        )
        self.dipole_hold_time: FloatParamHandle

        self.setattr_param(
            "dipole_pre_experiment_delay",
            FloatParam,
            "Time to delay experiment after dipole trap",
            default=0.0,
            unit="us",
        )
        self.dipole_pre_experiment_delay: FloatParamHandle

        # %% Fragments

        self.setattr_fragment(
            "constant_dipole_traps_setter",
            make_set_beams_to_default(
                suservo_beam_infos=[
                    constants.SUSERVOED_BEAMS["down_813"],
                    constants.SUSERVOED_BEAMS["dipole_trap_1064_delivery"],
                ],
                urukul_beam_infos=[
                    constants.URUKULED_BEAMS["dipole_trap_1064_freespace_AOM"]
                ],
                use_automatic_setup=False,
            ),
        )
        self.constant_dipole_traps_setter: SetBeamsToDefaults

        # Get rid of irrelevant delay after narrowband MOT
        self.override_param("expansion_time", 0)

    @kernel
    def do_experiment_after_red_mot_hook(self):
        self.dipole_trap_molasses_hook()
        self.dipole_trap_optical_pumping_hook()
        self.dipole_trap_evaporation_hook()
        delay(self.dipole_hold_time.get())
        self.post_dipole_trap_hook()
        delay(self.dipole_pre_experiment_delay.get())
        self.do_experiment_after_dipole_trap_hook()

    @kernel
    def dipole_trap_molasses_hook(self):
        """
        Hook for implementation of stages after the dipole trap molasses stage. By default, turn on the dipole trap beams.
        """
        self.constant_dipole_traps_setter.turn_on_all()

    @kernel
    def dipole_trap_optical_pumping_hook(self):
        """
        Hook for implementation of stages after the dipole trap optical pumping stage. By default, do nothing.
        """

    @kernel
    def dipole_trap_evaporation_hook(self):
        """
        Hook for implementation of stages after the dipole trap evaporation
        stage. By default, turn off all the red beams to allow holding in dipole
        trap before experiment.
        """
        self.dipole_trap_evaporation_hook_default()

    @kernel
    def post_dipole_trap_hook(self):
        """
        Hook for implementation of stages immediately after the dipole trap is
        released. By default, turn off the dipole trap beams.
        """
        self.post_dipole_trap_hook_default()

    @kernel
    def post_dipole_trap_hook_default(self):
        """
        Turn off the dipole trap beams

        Advances the timeline by a few coarse cycles
        """
        self.dipole_beam_controller.turn_off_dipole_beams()

    @kernel
    def dipole_trap_evaporation_hook_default(self):
        """
        By default, turn off all the red beams to allow holding in dipole trap before experiment
        """
        self.red_mot.red_beam_controller.turn_off_mot_beams(ignore_shutters=True)
        self.red_mot.red_beam_controller.turn_off_spin_pol(ignore_shutters=True)

    @abc.abstractmethod
    def do_experiment_after_dipole_trap_hook(self):
        """
        Hook for the implementation of the following cooling stages or
        whatever pulses, executed after the programmed expansion time is
        completed.
        """
        raise NotImplementedError


# %%
