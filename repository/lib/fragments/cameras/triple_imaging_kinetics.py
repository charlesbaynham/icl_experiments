import abc
import logging

from artiq.experiment import at_mu
from artiq.experiment import delay
from artiq.experiment import delay_mu
from artiq.experiment import kernel
from artiq.experiment import now_mu
from artiq.experiment import parallel
from artiq.experiment import sequential
from ndscan.experiment import FloatChannel
from ndscan.experiment.parameters import FloatParam
from ndscan.experiment.parameters import FloatParamHandle
from numpy import int64

from repository.lib import constants
from repository.lib.fragments.cameras.andor_camera import AndorCameraControl
from repository.red_mot.measure_red_mot import RedMOTBase

logger = logging.getLogger(__name__)


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
    """

    def build_fragment(self):
        # Set this frag up first, so that later fragments' device_setup override it
        self.pre_build_fragment_hook()

        super().build_fragment()

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

        for c in "xyz":
            self.setattr_param(
                f"{c}_coil_boost",
                FloatParam,
                default=0.0,
                description=f"Boost to {c} coil current",
                unit="A",
            )
        self.x_coil_boost: FloatParamHandle
        self.y_coil_boost: FloatParamHandle
        self.z_coil_boost: FloatParamHandle

    @kernel
    def run_once(self):
        self.before_start_hook()

        self.core.break_realtime()
        self._from_start_to_end_of_broadband_mot()

        # The FLIR cameras are not useful for the final imaging, so use them to
        # image the blue MOT instead
        delay(-self.red_broadband_time.get() - 10e-3)
        self.camera_interface.trigger()
        delay(+self.red_broadband_time.get() + 10e-3)

        # The Andor camera shutter needs ~120ms to open, so start this at the
        # beginning of the red stages. If the total red mot sequence takes less
        # time than this then we'll have problems
        delay(-self.red_broadband_time.get())
        self.andor_camera_control.set_shutter(True)
        delay(+self.red_broadband_time.get())

        self.blue_3d_mot.turn_off_repumpers()
        delay_mu(int64(self.core.ref_multiplier))
        self.red_mot.transition_broadband_to_narrowband()

        t_light_off_mu = now_mu()
        self.red_mot.red_beam_controller.turn_off_mot_beams(ignore_shutters=True)

        self.pre_expansion_hook()

        # Ensure that the expansion time isn't affected by durations of SPI
        # transfers etc.
        at_mu(t_light_off_mu)

        self.red_mot.chamber_2_field_setter.set_all_fields(
            self.spectroscopy_field_gradient.get(),
            self.blue_3d_mot.chamber_2_bias_x.get() + self.x_coil_boost.get(),
            self.blue_3d_mot.chamber_2_bias_y.get() + self.y_coil_boost.get(),
            self.blue_3d_mot.chamber_2_bias_z.get() + self.z_coil_boost.get(),
        )

        delay(self.expansion_time.get())

        # Do the spectroscopy / interfereometry / whatever sequence. This method
        # must be defined by child classes
        self.do_spectroscopy_hook()

        delay(self.delay_after_spectroscopy.get())

        self.do_imaging_hook()

        self.andor_camera_control.set_shutter(False)

        # Save blue MOT pics
        self.core.wait_until_mu(now_mu())
        self.camera_interface.save_data()

        self.save_data_hook()

        # TODO: Move this closing of red mot shutters somewhere more sensible
        self.core.break_realtime()
        self.red_mot.red_beam_controller.turn_off_mot_beams()

    @kernel
    def _do_pulse(self, andor_exposure):
        with parallel:
            with sequential:
                delay(-0.5 * andor_exposure)
                self.andor_camera_control.trigger(
                    exposure=andor_exposure,
                    control_shutter=False,
                )
                delay(0.5 * andor_exposure)

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
    def pre_expansion_hook(self):
        """
        Hook for core actions after the narrowband red mot is completed, before
        cloud expansion begins
        """
        pass

    @abc.abstractmethod
    def do_spectroscopy_hook(self):
        """
        Hook for the implementation of a spectroscopy / interfereometry /
        whatever pulse, executed after the programmed expansion time is
        completed.
        """
        raise NotImplementedError

    @kernel
    def do_first_pulse(self, andor_exposure):
        self._do_pulse(andor_exposure)

    @kernel
    def do_second_pulse(self, andor_exposure):
        self._do_pulse(andor_exposure)

    @kernel
    def do_third_pulse(self, andor_exposure):
        self._do_pulse(andor_exposure)


class TripleImageMOTFrag(RedMOTWithExperiment):
    def build_fragment(self):
        super().build_fragment()

        self.setattr_param(
            "delay_between_fluoresence_pulses",
            FloatParam,
            "Delay after first fluorescence pulse before second",
            default=1e-3,
            unit="ms",
        )
        self.delay_between_fluoresence_pulses: FloatParamHandle

        self.setattr_param(
            "delay_before_background_pulse",
            FloatParam,
            "Delay after final fluorescence pulse before background measurement",
            default=10e-3,
            unit="ms",
        )
        self.delay_before_background_pulse: FloatParamHandle

        self.setattr_result("andor_sum_0", FloatChannel)
        self.setattr_result("andor_sum_1", FloatChannel)
        self.setattr_result("andor_sum_2", FloatChannel)
        self.setattr_result("excitation_fraction", FloatChannel)
        self.andor_sum_0: FloatChannel
        self.andor_sum_1: FloatChannel
        self.andor_sum_2: FloatChannel
        self.excitation_fraction: FloatChannel

    @kernel
    def do_imaging_hook(self):
        """
        Hook for the imaging sequence. This hook runs after the spectroscopy
        etc. is completed, and should handle imaging with the Andor camera.
        """
        andor_exposure = 2 * self.fluorescence_pulse.fluorescence_pulse_duration.get()

        # Image ground state atoms
        self.do_first_pulse(andor_exposure)

        # Image excited state atoms
        delay(self.delay_between_fluoresence_pulses.get())
        self.do_second_pulse(andor_exposure)

        # Take background measurement
        delay(self.delay_before_background_pulse.get())
        self.do_third_pulse(andor_exposure)

    @kernel
    def save_data_hook(self):
        """
        Hook to save data from the Andor camera

        Runs in realtime after imaging is completed
        """
        # Save Andor data
        sums = [0] * 3
        means = [0.0] * 3
        self.andor_camera_control.readout_ROIs(
            sums,
            means,
            self.core.get_rtio_counter_mu() + self.core.seconds_to_mu(1.0),
        )

        self.andor_sum_0.push(sums[0])
        self.andor_sum_1.push(sums[1])
        self.andor_sum_2.push(sums[2])

        self.excitation_fraction.push(
            (means[1] - means[2]) / (means[0] + means[1] - 2 * means[2])
        )

    def hook_setup_andor(self):
        """
        Setup the Andor camera to use 3x ROIs since we're expecting fast
        kinetics mode with 3 images

        TODO: Set up Fast Kinetics mode here
        """

        # 3x ROIs
        self.setattr_fragment(
            "andor_camera_control",
            AndorCameraControl,
            roi_defaults=[
                [
                    constants.ANDOR_ROI_X0,
                    i * constants.ANDOR_FAST_KINETICS_HEIGHT,
                    constants.ANDOR_ROI_X1,
                    (i + 1) * constants.ANDOR_FAST_KINETICS_HEIGHT,
                ]
                for i in range(3)
            ],
        )
        self.andor_camera_control: AndorCameraControl


class SpectroscopyParamsMixin(RedMOTWithExperiment):
    """
    Adds parameters for controlling a spectroscopy pulse
    """

    def build_fragment(self):
        super().build_fragment()

        self.setattr_param(
            "spectroscopy_pulse_time",
            FloatParam,
            "Length of spectroscopy pulse",
            default=50e-6,
            unit="us",
        )
        self.spectroscopy_pulse_time: FloatParamHandle

        self.setattr_param(
            "spectroscopy_pulse_aom_detuning",
            FloatParam,
            "Frequency detuning of AOM during spectroscopy pulse",
            default=0,
            unit="kHz",
        )
        self.spectroscopy_pulse_aom_detuning: FloatParamHandle

        self.setattr_param(
            "spectroscopy_pulse_aom_amplitude",
            FloatParam,
            "Amplitude of delivery AOM during spectroscopy pulse. SUServoing is disabled",
            default=1.0,
            min=0.0,
            max=1.0,
        )
        self.spectroscopy_pulse_aom_amplitude: FloatParamHandle
