"""
This package provides a template experiment, :class:`~RedMOTWithExperiment` .
Unlike other modules, it *does not* provide a Fragment which you should use via
`self.setattr_fragment`. Instead, it defines an :class:`~ExpFragment` which
should be converted into an :class:`~EnvExperiment` using
:meth:`~make_fragment_scan_exp`.

:class:`~RedMOTWithExperiment` and its friends like
:class:`~DipoleTrapWithExperiment` are the basis of most of our complex
sequences. See the documentation for :class:`~RedMOTWithExperiment` for an
explanation of how they work.
"""

import abc
import logging

from artiq.coredevice.core import Core
from artiq.experiment import at_mu
from artiq.experiment import delay
from artiq.experiment import delay_mu
from artiq.experiment import kernel
from artiq.experiment import now_mu
from artiq.experiment import parallel
from artiq.experiment import sequential
from ndscan.experiment import ExpFragment
from ndscan.experiment.parameters import BoolParam
from ndscan.experiment.parameters import BoolParamHandle
from ndscan.experiment.parameters import FloatParam
from ndscan.experiment.parameters import FloatParamHandle
from numpy import int64
from pyaion.fragments.suservo import LibSetSUServoStatic

from repository.lib import constants
from repository.lib.fragments.blue_3d_mot import Blue3DMOTFrag
from repository.lib.fragments.checkpoint_fragment import RedMOTCheckpoints
from repository.lib.fragments.fluorescence_pulse import ToggleableFluorescencePulse
from repository.lib.fragments.red_mot import RedMOTThreePhaseFrag
from repository.lib.fragments.timestamp_synchronizer import Timestamper

logger = logging.getLogger(__name__)


class RedMOTWithExperiment(RedMOTCheckpoints, ExpFragment, abc.ABC):
    """
    Run a sequence that makes a red MOT, allows setting of expansion and coils,
    does something to it (e.g. a spectroscopy or interferometry sequence) then
    images it.

    Note that this is not a Fragment to be added as a subfragment, but an
    ExpFragment designed to be used as a top-level experiment but subclassed to
    control its features.

    There are two ways of customising the behaviour of this ExpFragment: Hooks
    and Checkpoints. Both Hooks and Checkpoints are executed at particular
    moments in the sequence. For example, there is a "post narrowband"
    Checkpoint which allow you to insert code to be executed just after the
    narrowband MOT is completed. There is also a :meth:`do_imaging_hook` which
    is responsible for imaging the atoms (if desired).

    The distinction is in their use and purpose:

    Checkpoints
    -----------

    * Checkpoints are moments in the code at which Subfragments can *add* code
      to be run.
    * `device_setup` is an example of a Checkpoint, but we also have access to
      more.
    * Checkpoints are for moments in a sequence where multiple things might need
      to happen. Ideally the order should be unimportant. If order does matter,
      you can ensure the execution order you want by manually defining the
      top-level checkpoint.
    * To run code in a Checkpoint, define a Subfragment which implements that
      Checkpoint's method and add it to the top-level experiment using
      `self.setattr_fragment`.

    Hooks
    -----

    * Hooks are moments in the code at which Mixins can *replace* code to be
      run.
    * Hooks are intended for performing an action such as "imaging the atoms" or
      "doing an interferometry sequence"
    * It usually does not make sense to do multiple things in a hook.
    * To run code in a Hook, override the hook in a new Mixin class and then add
      this class to your top-level experiment.

    Mixins
    ------

    Mixins also deserve a mention here - a mixin is an object-orientated concept
    where a subclass is intended to be added to another class, altering its
    behaviour. E.g. you might have:

    .. code-block:: python

        class Animal():
            def speak(self):
                print("???")

        class BarkingMixin(Animal):
            def speak(self):
                print("Woof!")

        class TailWaggingMixin(Animal):
            def wag_tail(self):
                print("\\")
                print("/")
                print("\\")
                print("/")
                print("\\")
                print("/")


    `Animal` is a normal class, `BarkingMixin` and `TailWaggingMixin` are mixins. To construct a dog, I might do:

    .. code-block:: python

        class Dog(BarkingMixin, TailWaggingMixin, Animal):
            pass

        d = Dog()
        d.speak()
        d.wag_tail()


    Note that `BarkingMixin` **modified** the behaviour of the `speak()` method
    whereas `TailWaggingMixin` added new functionality.

    In our code, we use Mixins to implement both Checkpoint and Hooks. For Hooks, we override methods
    like `Animal.speak` or `RedMOTWithExperiment.do_imaging_hook`, like this:

    .. code-block:: python

        class AndorImagingMixin():
            def do_imaging_hook(self):
                # Do the imaging with the Andor camera
                pass # write useful code here


        class MyAndorImagedLatticeExperiment(
            AndorImagingMixin,
            LatticeTrappingMixin,
            RedMOTWithExperiment
        ):
            pass


    Here, we wrote a "Mixin" which implemented a "Hook" called "do_imaging_hook".
    This allowed us to easily add imaging to our `MyAndorImagedLatticeExperiment`,
    which also selected different behaviour that was implemented by other mixins.

    For Checkpoints, we use our mixin to **extend**
    the top-level :meth:`~build_fragment`, adding our new CheckpointFragment. For
    example, maybe we want to print out the time when a certain checkpoint is reached:

    .. literalinclude:: ../../../repository/lib/experiment_templates/mixins/time_printing.py
       :language: python

    Example
    -------

    For a simple implementation see
    :class:`~repository.clock_spectroscopy.clock_spectroscopy_from_XODT.ClockSpecFromXXODTFrag`.

    For the Checkpoint example above, see :class:`repository.lib.experiment_templates.mixins.time_printing.TimePrintingMixin`.
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

        self.setattr_fragment("blue_3d_mot", Blue3DMOTFrag, manual_init=False)
        self.blue_3d_mot: Blue3DMOTFrag

        self.setattr_fragment("red_mot", RedMOTThreePhaseFrag)
        self.red_mot: RedMOTThreePhaseFrag

        self.setattr_fragment("fluorescence_pulse", ToggleableFluorescencePulse)
        self.fluorescence_pulse: ToggleableFluorescencePulse

        self.setattr_fragment(
            "clock_delivery_beam_suservo",
            LibSetSUServoStatic,
            constants.SUSERVOED_BEAMS["clock_delivery"].suservo_device,
        )
        self.clock_delivery_beam_suservo: LibSetSUServoStatic

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
            default=6e-6,
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

        self.hook_setup_andor()

    @kernel
    def device_setup(self) -> None:
        self.device_setup_subfragments()

        self.core.break_realtime()

        # Boost the clock delivery SUServo's gain
        # TODO: This should not be here
        self.clock_delivery_beam_suservo.set_iir_params(
            ki=constants.DEFAULT_CLOCK_DELIVERY_SUSERVO_PID_I
        )
        self.core.break_realtime()

        self.DMA_initialization_hook()

    @kernel
    def DMA_initialization_hook(self):
        """
        Preload phases' handles. These have to be grouped together, instead of
        handled in separate subfragment setups, otherwise only the last-compiled
        dma handle is valid.
        """
        self.blue_3d_mot.blue_transfer_MOT.precalculate_dma_handle()
        self.red_mot.broadband_red_phase.precalculate_dma_handle()
        self.red_mot.narrow_red_capture_phase.precalculate_dma_handle()
        self.red_mot.narrow_red_compression_phase.precalculate_dma_handle()

        self.DMA_initialization_hook_subfragments()

    @kernel
    def run_once(self):
        self.core.break_realtime()

        self.before_start_hook()  # FIXME: remove all uses of this and convert to device_setup

        self.core.break_realtime()

        # Mark the start of the blue MOT as the timestamp we record. This could
        # be changed to e.g. the start of the clock pulse in future.
        self.timestamper.mark_timestamp()

        if self.magnetic_trap_loading_bool.get():
            self.blue_3d_mot.load_magnetic_trap()
        else:
            self.blue_3d_mot.load_mot(clearout=True)
        self.end_of_blue_3d_mot_loading_hook()

        # Ramp down the blue MOT
        self.blue_3d_mot.do_blue_transfer_mot()

        # Keep the blue light on for a short time while turning on the red beams
        with parallel:
            # Turn off the blue beams, a little after the red MOT starts
            with sequential:
                delay(self.blue_3d_mot.delay_into_red_mot_for_blue_beam_switchoff.get())
                self.blue_3d_mot.turn_off_3d_and_2d_beams_nopush()
            # and start the red MOT
            with sequential:
                self.red_mot.prepare_for_broadband_phase()
                self.start_of_red_broadband_hook()
                self.red_mot.broadband_red_phase.do_phase()

        self.end_of_broadband_mot_hook()

        self.blue_3d_mot.turn_off_repumpers()
        delay_mu(int64(self.core.ref_multiplier))
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

        # Do the spectroscopy / interferometry / whatever sequence. This method
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
        self.save_flir_data_hook()  # FIXME combine with andor hook using checkpoint

        # This one for the Andor
        self.save_andor_data_hook()

        self.after_data_saved_checkpoint()

    # %% Hooks / overridable methods
    #
    # The remaining methods in this class are designed to be overridden by
    # children of this class, to control its behaviour. See `run_once` to
    # understand where these hooks are executed.
    #
    # Those marked with `abc.abstractmethod` are compulsory - python will not
    # allow you to construct children classes until those methods are
    # implemented
    #
    # Note that "Checkpoints" also exist: see RedMOTCheckpoints for more information.
    def hook_setup_andor(self):
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
        self.post_sequence_cleanup_hook_subfragments()

        # Reset the MOT beams to allow AOMs to settle before the next shot
        self.blue_3d_mot.all_beam_default_setter.turn_on_all(light_enabled=False)
        self.red_mot.red_beam_controller.all_beam_default_setter.turn_on_all(
            light_enabled=False
        )

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
    def post_narrowband_hook(self):  # FIXME Deal with this. Might be annoying
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
    def set_postnarrowband_fields_hook(self):
        """
        Hook for setting magnetic fields immediately after end of red MOT. This
        fires at the same cursor position as the pre_expansion_hook, and runs
        after it.

        Any changes to the cursor made by this function will be respected, i.e.
        the rest of the sequence CAN be delayed by this hook
        """
        self.set_postnarrowband_fields_hook_default()

    @kernel
    def set_postnarrowband_fields_hook_default(self):
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


# %%
