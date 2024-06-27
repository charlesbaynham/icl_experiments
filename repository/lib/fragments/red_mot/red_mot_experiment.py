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

from artiq.coredevice.core import Core
from artiq.experiment import at_mu
from artiq.experiment import delay
from artiq.experiment import delay_mu
from artiq.experiment import kernel
from artiq.experiment import now_mu
from artiq.experiment import parallel
from ndscan.experiment import ExpFragment
from ndscan.experiment import FloatChannel
from ndscan.experiment.parameters import FloatParam
from ndscan.experiment.parameters import FloatParamHandle
from numpy import int64

from repository.lib.constants import MIRNY_SETTINGS_87
from repository.lib.constants import MIRNY_SETTINGS_88
from repository.lib.fragments.blue_3d_mot import Blue3DMOTFrag
from repository.lib.fragments.cameras.andor_camera import AndorCameraControl
from repository.lib.fragments.fluorescence_pulse import ToggleableFluorescencePulse
from repository.lib.fragments.red_mot import NarrowbandRedMOTFrag
from repository.lib.fragments.set_eom_sidebands import SetEOMSidebandsFrag

logger = logging.getLogger(__name__)


class RedMOTBase(ExpFragment):
    def build_fragment(self) -> None:
        self.setattr_device("core")
        self.core: Core

        # %% Fragments

        self.setattr_fragment("blue_3d_mot", Blue3DMOTFrag, manual_init=False)
        self.blue_3d_mot: Blue3DMOTFrag

        self.setattr_fragment("red_mot", NarrowbandRedMOTFrag)
        self.red_mot: NarrowbandRedMOTFrag

        self.setattr_fragment("fluorescence_pulse", ToggleableFluorescencePulse)
        self.fluorescence_pulse: ToggleableFluorescencePulse

        # %% Params

        # Expansion time - can be negative
        self.setattr_param(
            "expansion_time",
            FloatParam,
            "Time to expand MOT for before imaging",
            default=0.0,
            unit="us",
        )
        self.expansion_time: FloatParamHandle

        # %% Rebound params

        self.setattr_param_rebind("injection_aom_static_frequency", self.red_mot)
        self.setattr_param_rebind(
            "red_broadband_time",
            self.red_mot.broadband_red_phase,
            "duration",
            description="Broadband phase duration",
        )
        self.red_broadband_time: FloatParamHandle

        self.hook_setup_andor()

    def hook_setup_andor(self):
        """
        Setup the Andor camera

        This is a method so that children classes can override it
        """
        self.setattr_fragment("andor_camera_control", AndorCameraControl)
        self.andor_camera_control: AndorCameraControl

        self.setattr_result("andor_sum", FloatChannel, display_hints={"priority": -1})
        self.setattr_result("andor_mean", FloatChannel)
        self.andor_sum: FloatChannel
        self.andor_mean: FloatChannel

    @kernel
    def _from_start_to_end_of_broadband_mot(self):
        self.blue_3d_mot.load_mot(clearout=True)
        self.blue_3d_mot.turn_off_3d_and_2d_beams()
        self.red_mot.prepare_for_broadband_phase()
        self.red_mot.broadband_red_phase.do_phase()


class SetEOMSidebandsExceptCavity(SetEOMSidebandsFrag):
    mirny_settings_87 = [
        s for s in MIRNY_SETTINGS_87 if "cavity_offset" not in s.device_name
    ]
    mirny_settings_88 = [
        s for s in MIRNY_SETTINGS_88 if "cavity_offset" not in s.device_name
    ]


class RedMOTWithExperiment(RedMOTBase, abc.ABC):
    """
    Run a sequence that makes a red MOT, allows setting of expansion and coils,
    does something to it (e.g. a spectroscopy or interferometry sequence) then
    images it.

    Note that this is not a Fragment to be added as a subfragment, but an
    ExpFragment designed to be used as a top-level experiment but subclassed to
    control its features.

    This ExpFragment cannot be used as is - you should subclass it and implement
    methods in your child class. You must implement these:

    * `do_spectroscopy_hook`
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
        # Set this frag up first, so that later fragments' device_setup override it
        self.pre_build_fragment_hook()

        super().build_fragment()

        self.setattr_fragment(
            "mirny_eom_sidebands", SetEOMSidebandsExceptCavity, init_mirnys=False
        )
        self.mirny_eom_sidebands: SetEOMSidebandsFrag

        self.setattr_param_rebind("sr87", self.mirny_eom_sidebands)

        self.setattr_param(
            "delay_after_spectroscopy",
            FloatParam,
            "Delay after spectroscopy before imaging",
            default=6e-6,
            unit="us",
        )
        self.delay_after_spectroscopy: FloatParamHandle

        self.setattr_param(
            "spectroscopy_field_gradient",
            FloatParam,
            "MOT coil current during spectroscopy",
            default=0.0,
            unit="A",
        )
        self.spectroscopy_field_gradient: FloatParamHandle

    @kernel
    def run_once(self):
        self.core.break_realtime()
        self.mirny_eom_sidebands.set_sidebands()

        self.before_start_hook()

        self.core.break_realtime()
        self._from_start_to_end_of_broadband_mot()

        delay(-self.red_broadband_time.get())
        self.start_of_red_broadband_hook()
        delay(+self.red_broadband_time.get())

        self.end_of_broadband_mot_hook()

        self.blue_3d_mot.turn_off_repumpers()
        delay_mu(int64(self.core.ref_multiplier))
        self.red_mot.transition_broadband_to_narrowband()

        # Do the post-narrowband actions. By default, turn off the red MOT light
        self.post_narrowband_hook()

        # Do any other pre-expansion actions. By default, none
        t_light_off_mu = now_mu()
        self.pre_expansion_hook()
        # Ensure that the expansion time isn't affected by durations of SPI
        # transfers etc.
        at_mu(t_light_off_mu)

        # Set magnetic fields for the rest of the sequence
        self.set_fields_hook()

        delay(self.expansion_time.get())

        # Do the spectroscopy / interfereometry / whatever sequence. This method
        # must be defined by child classes
        self.do_spectroscopy_hook()

        delay(self.delay_after_spectroscopy.get())

        self.do_imaging_hook()

        self.andor_camera_control.set_shutter(False)

        self.post_sequence_cleanup_hook()

        self.core.wait_until_mu(now_mu())
        # Normally I'd only have one hook for a given purpose, but since we
        # often want to do one thing with the FLIR camera and another with the
        # ANDOR, and since ARTIQ doesn't support inheritance properly, it's
        # easier to have two methods.
        # This one is intended for the FLIR cameras:
        self.save_flir_data_hook()

        # This one for the Andor
        self.save_data_hook()

    @kernel
    def do_pulse(self, andor_exposure):
        """
        Default implementation of a fluorescence pulse, available for use by
        mixins in :meth:`~do_imaging_hook` (but not used by default).
        """
        with parallel:
            self.andor_camera_control.trigger(
                exposure=andor_exposure,
                control_shutter=False,
            )
            self.fluorescence_pulse.do_imaging_pulse(ignore_final_shutters=True)

    # %% Hooks / overridable methods
    #
    # The remaining methods in this class are designed to be overridden by
    # children of this class, to control its behaviour. See `run_once` to
    # understand where these hooks are executed.
    #
    # Those marked with `abc.abstractmethod` are compulsory - python will not
    # allow you to construct children classes until those methods are
    # implemented

    def hook_setup_andor(self):
        """
        Setup the Andor camera

        This hook will run during `build_fragment` and must create an
        :class:`~AndorCameraControl` Fragment as an attribute named
        "andor_camera_control".

        By default, delegate to :class:`~RedMOTBase` which configures a single
        ROI.
        """
        return super().hook_setup_andor()

    @abc.abstractmethod
    def do_imaging_hook(self):
        """
        Hook for the imaging sequence. This hook runs after the spectroscopy
        etc. is completed, and should handle imaging with the Andor camera.
        """
        raise NotImplementedError

    @kernel
    def save_data_hook(self):
        """
        Hook to save data from the Andor camera

        Runs in realtime after imaging is completed
        """
        pass

    @kernel
    def save_flir_data_hook(self):
        """
        Run after the sequence has ended. This hook is intended to save data
        from the FLIR cameras.
        """
        pass

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

    def pre_build_fragment_hook(self):
        """
        Hook run at the beginning of `build_fragment`

        TODO: Remove this, users can just override build_fragment and user
        `super()` as god intended.
        """
        pass

    @kernel
    def before_start_hook(self):
        """
        Hook for core actions before the start of the atomics sequence.

        Feel free to use break_realtime - it will be called again before the MOT
        is loaded.
        """
        pass

    @kernel
    def end_of_broadband_mot_hook(self):
        """
        Executed immediately after the broadband MOT stage ends, before the
        broadband ramping is disabled. No timeline correction is performed, so
        changes here will delay the narrowband red MOT.
        """
        pass

    @kernel
    def start_of_red_broadband_hook(self):
        """
        Executed as the broadband MOT stage starts.

        This hook is called after the broadband MOT phase has already been
        queued into the RTIO, so write here will consume new lanes.

        TODO: Move this hook so that new lanes aren't needed
        """
        pass

    @kernel
    def post_narrowband_hook(self):
        """
        Hook for core actions after the narrowband red mot is completed, before
        the light is turned off

        Any changes to the cursor made by this function will be respected, i.e.
        the rest of the sequence CAN be delayed by this hook

        By default, just turn off the red light
        """
        self.default_post_narrowband_hook()

    @kernel
    def default_post_narrowband_hook(self):
        self.red_mot.red_beam_controller.turn_off_mot_beams(ignore_shutters=True)

    @kernel
    def pre_expansion_hook(self):
        """
        Hook for core actions after the narrowband red mot is completed, after
        the light is turned off and cloud expansion begins

        Any changes to the cursor made by this hook will be ignored
        """
        pass

    @kernel
    def set_fields_hook(self):
        """
        Hook for setting magnetic fields immediately after end of red MOT. This
        fires at the same cursor position as the pre_expansion_hook, and runs
        after it.

        Any changes to the cursor made by this function will be respected, i.e.
        the rest of the sequence CAN be delayed by this hook
        """

        self.red_mot.chamber_2_field_setter.set_mot_gradient(
            self.spectroscopy_field_gradient.get()
        )

    @abc.abstractmethod
    def do_spectroscopy_hook(self):
        """
        Hook for the implementation of a spectroscopy / interfereometry /
        whatever pulse, executed after the programmed expansion time is
        completed.
        """
        raise NotImplementedError


# %%
