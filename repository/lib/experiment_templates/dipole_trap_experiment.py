"""
This package provides a template experiment, :class:`~RedMOTWithExperiment` .
Unlike other modules, it *does not* provide a Fragment which you should use via
`self.setattr_fragment`. Instead, it defines an :class:`~ExpFragment` which should be
converted into an :class:`~EnvExperiment` using :meth:`~make_fragment_scan_exp`.

The :class:`~ExpFragment`s that this module defines cannot be used without some
customization first. The :meth:`~build_fragment`, :meth:`~device_setup` and
:meth:`~run_once` methods of these :class:`ExpFragment` s contain "hooks" -
methods which can (or sometimes must) be implemented by child classes to alter
the functionality of these experiment. This allows you to reuse this code for
multiple different experiments by implementing child classes which define these
hooks in different ways.

For example, see the documentation of :class:`~RedMOTWithExperiment` for the
most basic implementation of hooks.

Mixins
------

This structure of overriding methods allows the use of "mixins". These are
classes which implement various pieces of functionality, which can be selected
from when authoring an experiment.

For example, you might author a mixin that adds imaging with the Andor camera
and another which causes atoms to be trapped in a lattice at the end of the MOT.
Your experiment might then inherit from both of these, to use both features at
the same time::

    from somewhere import AndorImagingMixin, LatticeTrappingMixin


    class MyAndorImagedLatticeExperiment(
        AndorImagingMixin,
        LatticeTrappingMixin,
        RedMOTWithExperiment
    ):
        pass

"""

import abc
import logging

from artiq.language import delay
from artiq.language import kernel
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
    Run a sequence that makes a red MOT, dipole trap, and then
    does something to it (e.g. a spectroscopy or interferometry sequence) then
    images it.

    Note that this is not a Fragment to be added as a subfragment, nor can it be used as is - you should subclass it and implement
    methods in your child class. You must implement these:

    * `do_experiment_after_dipole_trap_hook`
    * `do_imaging_hook`

    You probably want to implement:

    * `save_data_hook`

    And you may wish to implement other `..._hook` methods.

    Example
    -------

    For a simple implementation see
    :class:`~repository.clock_spectroscopy.clock_spectroscopy.BasicClockSpectroscopyExp`.
    """

    def build_fragment(self):
        super().build_fragment()

        # Hold time in dipole trap - can be negative
        self.setattr_param(
            "dipole_hold_time",
            FloatParam,
            "Time to hold final dipole trap before experiment",
            default=constants.DIPOLE_TRAP_HOLD_TIME,
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

        self.setattr_fragment("dipole_beam_controller", DipoleBeamController)
        self.dipole_beam_controller: DipoleBeamController

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
        self.constant_dipole_traps_setter: SetBeamsToDefaults  # FIXME This is duplicated in dipole_trap_beam_controller

        # Get rid of irrelevant delay after narrowband MOT
        self.override_param("expansion_time", 0)

    @kernel
    def do_experiment_after_red_mot_hook(self):
        self.dipole_trap_loading_hook()
        self.dipole_trap_molasses_hook()
        self.do_clearout_pulse_hook()
        self.dipole_trap_optical_pumping_hook()
        self.dipole_trap_evaporation_hook()
        delay(self.dipole_hold_time.get())
        self.post_dipole_trap_hook()
        delay(self.dipole_pre_experiment_delay.get())
        self.do_experiment_after_dipole_trap_hook()

    @kernel
    def dipole_trap_loading_hook(self):
        """
        Hook for implementation of stages after the dipole trap loading stage. By default, turn on the dipole trap beams.
        """
        self.constant_dipole_traps_setter.turn_on_all()

    @kernel
    def dipole_trap_molasses_hook(self):
        """
        Hook for implementation of stages after the dipole trap molasses stage. By default, turn on the dipole trap beams.
        """
        self.constant_dipole_traps_setter.turn_on_all()

    @kernel
    def do_clearout_pulse_hook(self):
        """
        Hook for implementation of a clearout pulse with 689.
        """

    @kernel
    def dipole_trap_optical_pumping_hook(self):
        """
        Hook for implementation of stages after the dipole trap optical pumping stage. By default, do nothing.
        """

    @kernel
    def dipole_trap_evaporation_hook(self):
        """
        Hook for implementation of stages after the dipole trap evaporation stage. By default, do nothing.
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
