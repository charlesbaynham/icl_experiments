"""
This package provides a template experiment, :class:`~RedMOTWithExperimentBase` .
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

For example, see the documentation of :class:`~RedMOTWithExperimentBase` for the
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
        RedMOTWithExperimentBase
    ):
        pass

"""

import abc
import logging

from artiq.language import delay
from artiq.language import kernel
from artiq.language import portable
from ndscan.experiment.parameters import FloatParam
from ndscan.experiment.parameters import FloatParamHandle
from numpy import int64

from repository.lib import constants
from repository.lib.experiment_templates.dma_actions_after_drop import (
    DMAActionsAfterDropMixin,
)
from repository.lib.experiment_templates.mixins.external_triggering import (
    External50HzTriggerMixin,
)
from repository.lib.fragments.dipole_trap.dipole_trap_beam_controller import (
    DipoleBeamController,
)
from repository.lib.experiment_templates.mixins.constant_lattice import (
    ConstantBeamsMixin,
)

logger = logging.getLogger(__name__)

BUFFER_DEPTH = 300


class DipoleTrapWithExperimentBase(ConstantBeamsMixin,External50HzTriggerMixin, DMAActionsAfterDropMixin):
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
            "Time to delay experiment after dipole trap or launch",
            default=925e-6,
            unit="us",
        )
        self.dipole_pre_experiment_delay: FloatParamHandle

        # %% Fragments

        self.setattr_fragment("dipole_beam_controller", DipoleBeamController)
        self.dipole_beam_controller: DipoleBeamController

        # Get rid of irrelevant delay after narrowband MOT
        self.override_param("expansion_time", 0)

        # The dipole drop (t_dipole_beams_off) is stamped by the active clock
        # mixin INSIDE the DMA recording, so it is recording-relative; the live
        # release time is t_playback_start_mu + t_dipole_beams_off (see
        # get_t_release_mu). Defaulted here so non-clock dipole experiments
        # still construct; the clock mixins overwrite it each shot. The DMA
        # recording fragment and clock-tracking state come from
        # DMAActionsAfterDropMixin.
        if not hasattr(self, "t_dipole_beams_off"):
            self.t_dipole_beams_off = int64(0)

    @kernel
    def DMA_initialization_hook(self):
        self.DMA_initialization_hook_redmot_default()
        self.DMA_initialization_hook_dipole_trap_default()

    @kernel
    def DMA_initialization_hook_dipole_trap_default(self):
        # The after-drop handle fetch. Kept as a named sub-hook because the many
        # dipole experiments that override DMA_initialization_hook chain it.
        self.dma_recording_fragment.DMA_initialization_hook_after_drop()

    @kernel
    def actions_after_drop(self):
        """
        Split out the parts of the sequence that occur after the atoms are
        dropped so that we can pre-record them in DMA. This allows us to:

        a) playback quickly
        b) know in advance the timings so we can calculate corrected ROI positions

        Note that because this is DMA, we cannot use RPC here
        """

        self.post_dipole_trap_hook()
        self.launch_hook()
        delay(self.dipole_pre_experiment_delay.get())
        self.do_experiment_after_dipole_trap_hook()

    @kernel
    def do_experiment_after_red_mot_hook(self):
        self.dipole_trap_loading_hook()
        self.dipole_trap_molasses_hook()
        self.dipole_trap_optical_pumping_hook()
        self.dipole_trap_evaporation_hook()
        self.adiabatic_cooling_hook()
        delay(self.dipole_hold_time.get())
        self.matterwave_collimate_hook()

        # Load the trap on the live timeline first (above), then play back the
        # pre-recorded `actions_after_drop`.
        self.play_actions_after_drop()

    @kernel
    def dipole_trap_loading_hook(self):
        """
        Hook for implementation of stages in the dipole trap loading stage. By default, turn on the dipole trap beams.
        """
        self.dipole_beam_controller.turn_on_dipole_beams()

    @kernel
    def dipole_trap_molasses_hook(self):
        """
        Hook for implementation of stages in the dipole trap molasses stage. By default, do nothing
        """

    @kernel
    def dipole_trap_optical_pumping_hook(self):
        """
        Hook for implementation of stages after the dipole trap optical pumping stage. By default, do nothing.
        """

    @kernel
    def dipole_trap_evaporation_hook(self):
        """
        Hook for implementation of evaporation in the dipole trap.

        By default, turn off all the red beams to allow holding in dipole trap before experiment
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
    def adiabatic_cooling_hook(self):
        """
        Hook for adiabatic colling.
        By default, do nothing.
        """

    @kernel
    def matterwave_collimate_hook(self):
        """
        Hook for matterwave collimation of the atoms.
        By default, do nothing.
        """

    # ------------------------------------------------------------------
    # Timebase accessor for the dynamic-ROI predictor (DynamicROIImagingMixin).
    # The release time is dipole-specific (overrides the mixin default); the
    # playback-start accessor and the DMA / clock-tracking machinery come from
    # DMAActionsAfterDropMixin.
    # ------------------------------------------------------------------

    @portable
    def get_t_release_mu(self) -> int64:
        """Live-timeline time the atoms were released (dipole beams off).

        The drop is stamped by the active clock mixin inside the DMA
        recording, so ``t_dipole_beams_off`` is recording-relative; its live
        time is the playback-start cursor plus that offset.
        """
        return self.t_playback_start_mu + self.t_dipole_beams_off

    @portable
    def get_t_release_minus_playback_mu(self) -> int64:
        """Release time relative to the DMA playback origin, in machine units.

        Equals ``t_release_mu - t_playback_start_mu``. The dynamic-ROI
        predictor needs only this difference (the absolute playback cursor
        cancels), so it can run in ``before_start_hook`` before either live
        timestamp is stamped. For the dipole path the drop is stamped inside
        the recording, so the offset is simply ``+t_dipole_beams_off``
        (available after the DMA recording completes).
        """
        return self.t_dipole_beams_off

    @kernel
    def post_dipole_trap_hook_default(self):
        """
        Turn off the dipole trap beams

        Advances the timeline by a few coarse cycles
        """
        self.dipole_beam_controller.turn_off_dipole_beams()
        # maybe add delay
        delay(8e-9)
        self.dipole_beam_controller.turn_off_painter_suservo()
        delay(8e-9)
        self.dipole_beam_controller.turn_off_vertical_up_suservo()

    @kernel
    def dipole_trap_evaporation_hook_default(self):
        """
        Turn off all the red beams to allow holding in dipole trap before experiment

        Advances the timeline by a few coarse cycles
        """
        self.red_mot.red_beam_controller.turn_off_mot_beams(ignore_shutters=True)
        self.red_mot.red_beam_controller.turn_off_spin_pol(ignore_shutters=True)
        self.dipole_beam_controller.turn_off_vertical_up_suservo()

    @abc.abstractmethod
    def do_experiment_after_dipole_trap_hook(self):
        """
        Hook for the implementation of the following cooling stages or
        whatever pulses, executed after the programmed expansion time is
        completed.
        """
        raise NotImplementedError
