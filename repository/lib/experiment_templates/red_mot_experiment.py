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

from artiq.coredevice.core import Core
from artiq.language import at_mu
from artiq.language import delay
from artiq.language import kernel
from artiq.language import now_mu
from artiq.language import parallel
from artiq.language import sequential
from ndscan.experiment import ExpFragment
from ndscan.experiment.parameters import BoolParam
from ndscan.experiment.parameters import BoolParamHandle
from ndscan.experiment.parameters import FloatParam
from ndscan.experiment.parameters import FloatParamHandle

from repository.lib.fragments.blue_3d_mot import Blue3DMOTFrag
from repository.lib.fragments.check_for_relocks import CheckForRelocksFrag
from repository.lib.fragments.fluorescence_pulse import ToggleableFluorescencePulse
from repository.lib.fragments.red_mot import RedMOTThreePhaseFrag
from repository.lib.fragments.timestamp_synchronizer import Timestamper

logger = logging.getLogger(__name__)


class RedMOTWithExperimentBase(ExpFragment, abc.ABC):
    """
    Run a sequence that makes a red MOT, allows setting of expansion and coils,
    does something to it (e.g. a spectroscopy or interferometry sequence) then
    images it.

    Note that this is not a Fragment to be added as a subfragment, but an
    ExpFragment designed to be used as a top-level experiment but subclassed to
    control its features.

    This ExpFragment cannot be used as is - you should subclass it and implement
    methods in your child class. You must implement these:

    * `do_experiment_after_red_mot_hook`

    You probably want to implement:

    * `save_data_hook`
    * `do_imaging_hook`

    And you may wish to implement other `..._hook` methods.

    Example
    -------

    For a simple implementation see
    :class:`~repository.clock_spectroscopy.clock_spectroscopy.BasicClockSpectroscopyExp`.
    """

    image_store: list[list] = []  # for putting e.g. Andor images in

    def build_fragment(self):
        self.setattr_device("core")
        self.core: Core

        self.setattr_device("led0")
        self.setattr_device("led1")

        # %% Fragments

        self.setattr_fragment("timestamper", Timestamper, automatic_timestamp=False)
        self.timestamper: Timestamper

        self.setattr_fragment("relock_checker", CheckForRelocksFrag)
        self.relock_checker: CheckForRelocksFrag

        self.setattr_fragment("blue_3d_mot", Blue3DMOTFrag, manual_init=False)
        self.blue_3d_mot: Blue3DMOTFrag

        self.setattr_fragment("red_mot", RedMOTThreePhaseFrag)
        self.red_mot: RedMOTThreePhaseFrag

        self.setattr_fragment("fluorescence_pulse", ToggleableFluorescencePulse)
        self.fluorescence_pulse: ToggleableFluorescencePulse

        # %% Params

        # Expansion time - can be negative
        self.setattr_param(
            "expansion_time",
            FloatParam,
            "Time to wait before experiment",
            default=0.0,
            unit="us",
        )
        self.expansion_time: FloatParamHandle

        # %% Rebound params

        self.setattr_param_rebind("injection_aom_static_frequency", self.red_mot)

        self.setattr_param_rebind(
            "blue_loading_time",
            self.blue_3d_mot,
            "loading_time",
            description="Blue MOT loading time",
        )
        self.blue_loading_time: FloatParamHandle

        self.setattr_param(
            "magnetic_trap_loading_bool",
            BoolParam,
            "Load via magnetic trap instead of blue MOT",
            default=False,
        )
        self.magnetic_trap_loading_bool: BoolParamHandle

        self.setattr_param_rebind("sr87", self.blue_3d_mot)

        self.setattr_param(
            "delay_after_experiment",
            FloatParam,
            "Delay after experiment before imaging",
            default=3900e-6,
            unit="us",
        )
        self.delay_after_experiment: FloatParamHandle

        self.setattr_param(
            "spectroscopy_field_gradient",
            FloatParam,
            "MOT coil current during spectroscopy",
            default=0.0,
            unit="A",
        )
        self.spectroscopy_field_gradient: FloatParamHandle

        self.red_mot.broadband_red_phase.bind_param(
            "bias_field_x_start", self.blue_3d_mot.chamber_2_bias_x
        )
        self.red_mot.broadband_red_phase.bind_param(
            "bias_field_y_start", self.blue_3d_mot.chamber_2_bias_y
        )
        self.red_mot.broadband_red_phase.bind_param(
            "bias_field_z_start", self.blue_3d_mot.chamber_2_bias_z
        )

        self.red_mot.broadband_red_phase.bind_param(
            "bias_field_x_end", self.red_mot.narrowband_bias_x
        )
        self.red_mot.broadband_red_phase.bind_param(
            "bias_field_y_end", self.red_mot.narrowband_bias_y
        )
        self.red_mot.broadband_red_phase.bind_param(
            "bias_field_z_end", self.red_mot.narrowband_bias_z
        )

        self.setup_andor_hook()

        self._first_run = True

    @kernel
    def device_setup(self) -> None:
        self.device_setup_subfragments()

        self.core.break_realtime()

        self.DMA_initialization_hook()

    @kernel
    def DMA_initialization_hook(self):
        """
        Preload phases' handles. These have to be grouped together, instead of
        handled in separate subfragment setups, otherwise only the last-compiled
        dma handle is valid.
        """
        self.DMA_initialization_hook_redmot_default()

    @kernel
    def DMA_initialization_hook_redmot_default(self):
        self.blue_3d_mot.blue_transfer_MOT.precalculate_dma_handle()
        self.red_mot.broadband_red_phase.precalculate_dma_handle()
        self.red_mot.narrow_red_capture_phase.precalculate_dma_handle()
        self.red_mot.narrow_red_compression_phase.precalculate_dma_handle()

    @kernel
    def run_once(self):
        self.core.break_realtime()

        self.before_start_hook()

        self.core.break_realtime()

        self.pre_sequence_hook()

        self.timestamper.mark_timestamp()

        if self.magnetic_trap_loading_bool.get():
            self.blue_3d_mot.load_magnetic_trap()
        else:
            self.blue_3d_mot.load_mot(clearout=True)
        self.end_of_blue_3d_mot_loading_hook()

        # The ordering here looks odd because we're working around lane
        # constraints. The blue transfer MOT phase will queue lots of events
        # into the RTIO lanes, filling them completely. If lane spreading were
        # enabled, that would prevent us going backwards in time. Since we often
        # go back in time in our code, we run with lane spreading disabled.
        # However that means that the processor must wait for the lane to empty
        # out before more events can be queued, causing an underflow. To avoid
        # this, we first schedule the start of the red MOT (which is light on
        # lane usage), then go back in time to schedule the blue MOT transfer.
        # This is heavy on lane usage and consumes a new lane, but that's fine.

        t_start_blue_rampdown_mu = now_mu()
        t_end_blue_rampdown_mu = t_start_blue_rampdown_mu + self.core.seconds_to_mu(
            self.blue_3d_mot.blue_transfer_MOT.get_duration()
        )

        # Keep the blue light on for a short time while turning on the red beams
        at_mu(t_end_blue_rampdown_mu)
        with parallel:
            # Start the red MOT
            with sequential:
                # Turn on the red beams and start ramping them
                self.red_mot.prepare_for_broadband_phase()
                # Hook for mixins to use - default nothing
                self.start_of_red_broadband_hook()
                # Save the time now so we can come back to it
                t_red_light_on = now_mu()
            # Turn off the blue beams, a little after the red MOT starts
            with sequential:
                delay(self.blue_3d_mot.delay_into_red_mot_for_blue_beam_switchoff.get())
                self.blue_3d_mot.turn_off_all_beams()

        # Go back to the start of the blue MOT rampdown, before all the red beam stuff above
        at_mu(t_start_blue_rampdown_mu)

        # Ramp down the blue MOT
        self.blue_3d_mot.do_blue_transfer_mot()

        # Continue the broadband phase as a GenericRampingPhase, for
        # compatibility with the rest of the sequence
        at_mu(t_red_light_on)
        self.red_mot.broadband_red_phase.do_phase()

        self.end_of_broadband_mot_hook()

        self.red_mot.terminate_broadband_mot()
        self.set_narrowband_fields_hook()
        self.red_mot.do_narrowband_red_mot()

        # Could be merged with post_narrowband_hook, but fairly harmless to leave as is for legacy code
        self.set_postnarrowband_fields_hook()
        # Do the post-narrowband actions. By default, turn off the red MOT light
        self.post_narrowband_hook()

        # Do any other pre-expansion actions. By default, none
        t_light_off_mu = now_mu()

        self.pre_expansion_hook()

        # Ensure that the expansion time isn't affected by durations of SPI
        # transfers etc.
        at_mu(t_light_off_mu)

        delay(self.expansion_time.get())

        # Do the spectroscopy / interfereometry / whatever sequence. This method
        # must be defined by child classes
        self.do_experiment_after_red_mot_hook()

        delay(self.delay_after_experiment.get())
        self.do_imaging_hook()
        self.post_sequence_cleanup_hook()

        self.core.wait_until_mu(now_mu())
        # Normally I'd only have one hook for a given purpose, but since we
        # often want to do one thing with the FLIR camera and another with the
        # ANDOR, and since ARTIQ doesn't support inheritance properly, it's
        # easier to have two methods.
        # This one is intended for the FLIR cameras:
        self.save_flir_data_hook()

        # This one for the Andor
        self.save_andor_data_hook()

        # Do extra functions at end of experiment
        self.host_functions_after_experiment_hook()

    # %% Hooks / overridable methods
    #
    # The remaining methods in this class are designed to be overridden by
    # children of this class, to control its behaviour. See `run_once` to
    # understand where these hooks are executed.
    #
    # Those marked with `abc.abstractmethod` are compulsory - python will not
    # allow you to construct children classes until those methods are
    # implemented

    def setup_andor_hook(self):
        """
        Setup the Andor camera

        This hook will run during `build_fragment` and must create an
        :class:`~AndorCameraControl` Fragment as an attribute named
        "andor_camera_control".

        By default, do nothing.
        """

    @kernel
    def do_imaging_hook(self):
        """
        Hook for the imaging sequence. This hook runs after the spectroscopy
        etc. is completed, and should handle imaging with the Andor camera.
        """
        with parallel:
            self.do_imaging_hook_andor()
            self.do_imaging_hook_flir()

    @kernel
    def do_imaging_hook_andor(self):
        pass

    @kernel
    def do_imaging_hook_flir(self):
        pass

    @kernel
    def save_andor_data_hook(self):
        """
        Hook to save data from the Andor camera

        Runs in realtime after imaging is completed
        """

    @kernel
    def save_flir_data_hook(self):
        """
        Run after the sequence has ended. This hook is intended to save data
        from the FLIR cameras.
        """

    @kernel
    def post_sequence_cleanup_hook(self):
        """
        Run after each sequence is completed
        """
        self.post_sequence_cleanup_hook_base()

    @kernel
    def post_sequence_cleanup_hook_base(self):
        self.core.break_realtime()
        self.blue_3d_mot.all_beam_default_setter.turn_on_all(light_enabled=False)
        self.red_mot.red_beam_controller.all_beam_default_setter.turn_on_all(
            light_enabled=False
        )

    @kernel
    def before_start_hook(self):
        """
        Hook for core actions before the start of the atomics sequence.

        Feel free to use break_realtime - it will be called again before the MOT
        is loaded.
        """

    @kernel
    def pre_sequence_hook(self):
        """
        Hook for core actions that can affect the timeline at the start of the sequence

        In contrast to :meth:`~before_start_hook`, break_realtimes will affect the sequence timeline from this point onwards.
        """

    @kernel
    def end_of_blue_3d_mot_loading_hook(self):
        """
        Executed when the loading blue MOT ends, as the ramping blue MOT phase begins.

        This will clash with the blue ramping phase: only add events here if you include a negative delay
        """

    @kernel
    def start_of_red_broadband_hook(self):
        """
        Executed as the broadband MOT stage starts.

        This hook is just before the broadband MOT starts. It should take
        negligible duration (i.e. just a few coarse RTIO cycles) otherwise
        assumptions about the broadband MOT duration will be wrong
        """

    @kernel
    def end_of_broadband_mot_hook(self):
        """
        Executed immediately after the broadband MOT stage ends, before the
        broadband ramping is disabled. No timeline correction is performed, so
        changes here will delay the narrowband red MOT.
        """

    @kernel
    def set_narrowband_fields_hook(self):
        """
        Hook for setting magnetic fields after the broadband for use in the narrowband MOT. This
        fires at the same cursor position as the pre_expansion_hook, and runs
        after it.

        Any changes to the cursor made by this function will be respected, i.e.
        the rest of the sequence CAN be delayed by this hook
        """
        self.set_narrowband_fields_default()

    @kernel
    def set_narrowband_fields_default(self):
        """
        Set the magnetic fields for the narrowband MOT to the default values
        """
        bias_x = self.red_mot.narrowband_bias_x.get()
        bias_y = self.red_mot.narrowband_bias_y.get()
        bias_z = self.red_mot.narrowband_bias_z.get()
        self.red_mot.chamber_2_field_setter.set_bias_fields(bias_x, bias_y, bias_z)
        delay(1.5e-6 + (808e-9 * 3))

    @kernel
    def post_narrowband_hook(self):
        """
        Hook for core actions after the narrowband red mot is completed, before
        the light is turned off

        Any changes to the cursor made by this function will be respected, i.e.
        the rest of the sequence CAN be delayed by this hook

        By default, just turn off the red light
        """
        self.post_narrowband_hook_default()

    @kernel
    def post_narrowband_hook_default(self):
        """
        Turns off the red MOT beams. This advances the timeline by one
        self.core.ref_multiplier, but includes several events in the future:
        Simultaneous commands will populate new lanes.
        """
        self.red_mot.red_beam_controller.turn_off_mot_beams(ignore_shutters=True)

    @kernel
    def pre_expansion_hook(self):
        """
        Hook for core actions after the narrowband red mot is completed, after
        the light is turned off and cloud expansion begins

        Any changes to the cursor made by this hook will be ignored
        """

    @kernel
    def set_postnarrowband_fields_hook(self):
        """
        Hook for setting magnetic fields immediately after end of red MOT. This
        fires at the same cursor position as the pre_expansion_hook, and runs
        after it.

        Any changes to the cursor made by this function will be respected, i.e.
        the rest of the sequence CAN be delayed by this hook
        """
        self.set_fields_default()

    @kernel
    def set_fields_default(self):
        self.red_mot.chamber_2_field_setter.set_mot_gradient(
            self.spectroscopy_field_gradient.get()
        )

    @abc.abstractmethod
    def do_experiment_after_red_mot_hook(self):
        """
        Hook for the implementation of the following cooling stages or
        whatever pulses, executed after the programmed expansion time is
        completed.
        """
        raise NotImplementedError

    @kernel
    def host_functions_after_experiment_hook(self):
        """
        Hook for doing any extra functions at the end of the experiment.
        """
        self.host_functions_after_experiment_hook_default()

    @kernel
    def host_functions_after_experiment_hook_default(self):
        """
        Default implementation of the host functions after experiment hook
        """
        self.relock_checker.check_and_log_relocks()
        # if relocks != 0:
        #     raise TransitoryError


# %%
