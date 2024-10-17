import abc
import logging

from artiq.experiment import kernel
from artiq.experiment import now_mu
from artiq.experiment import parallel
from artiq.experiment import rpc
from ndscan.experiment.parameters import BoolParamHandle

from repository.lib.experiment_templates.red_mot_experiment import RedMOTWithExperiment
from repository.lib.fragments.cameras.andor_camera import AndorCameraControl

logger = logging.getLogger(__name__)


DATASET_NAME = "andor_monitor_image"


class AndorImagingBase(RedMOTWithExperiment):
    """
    Base class for imaging with the Andor camera

    This base class defines the interface for imaging using the Andor camera in an
    experiment template.

    Using this class alone will not result in a working experiment, but this base
    class provides the hooks that subsequent imaging mixing can use and common setup
    shared between other types of imaging.

    This is a mixin - see the documentation for :mod:`~.red_mot_experiment` for
    details.

    Kernel hooks used (multiple mixins cannot use the same hooks):

    * :meth:`~do_imaging_hook_andor`
    * :meth:`~save_andor_data_hook`
    """

    def hook_setup_andor(self):
        """
        Setup the Andor camera

        This is a method so that children classes can override it
        """
        self.setattr_fragment("andor_camera_control", AndorCameraControl)
        self.andor_camera_control: AndorCameraControl

        self.setattr_device("ccb")

        self.setattr_param_rebind("use_andor_driver", self.andor_camera_control)
        self.use_andor_driver: BoolParamHandle

    def host_setup(self):
        if self.use_andor_driver.get():
            self.ccb.issue(
                "create_applet",
                "Single Andor image",
                f"${{artiq_applet}}image {DATASET_NAME}",
            )
        super().host_setup()

    @kernel
    def start_of_red_broadband_hook(self):
        # The Andor camera shutter needs ~120ms to open, so start this at the
        # beginning of the red stages. If the total red mot sequence takes less
        # time than this then we'll have problems
        self.andor_camera_control.set_shutter(True)

    @kernel
    def do_pulse(self):
        """
        Default implementation of a fluorescence pulse, available for use by
        mixins (but not used by default).
        """
        with parallel:
            self.andor_camera_control.trigger(
                exposure=self.fluorescence_pulse.fluorescence_pulse_duration.get(),
                control_shutter=False,
            )
            self.fluorescence_pulse.do_imaging_pulse(ignore_final_shutters=True)

    # In red_mot_experiment this is optional, but we make it compulsory here
    # since using this base class alone should be an error
    @abc.abstractmethod
    def do_imaging_hook_andor(self):
        pass

    @kernel
    def post_sequence_cleanup_hook(self):
        self.post_sequence_cleanup_hook_base()
        self.post_sequence_cleanup_hook_andor()

    @kernel
    def post_sequence_cleanup_hook_andor(self):
        # Ensure shutter is closed, though it should be anyway
        self.core.break_realtime()
        self.andor_camera_control.set_shutter(False)

    @rpc(flags={"async"})
    def _call_camera_rpc(self):
        # FIXME: Needs to support a generic number of pictures
        # TBC what to do about the monitor

        if self.use_andor_driver.get():
            # Read out the image, write it to the result channels and plot it in a viewer applet
            img_array = self.andor_camera_control.readout_image(timeout=1)
            sum_slice_x, sum_slice_y = self.andor_camera_control.slice_image(img_array)

            self.andor_sum_slice_x.push(sum_slice_x)
            self.andor_sum_slice_y.push(sum_slice_y)

            if self.andor_camera_control.save_raw_andor_image.get():
                self.andor_image.push(img_array)
            else:
                self.andor_image.push([])

            self.set_dataset(
                DATASET_NAME,
                img_array,
                broadcast=True,
                persist=False,
                archive=False,
            )
        else:
            # We must always push something to ResultChannels, so push something empty
            self.andor_sum_slice_x.push([])
            self.andor_sum_slice_y.push([])
            self.andor_image.push([])

    @kernel
    def save_andor_data_hook(self):
        "Consume all slack and save the photos"

        # FIXME Needs to support a generic number of ROIs

        self.core.wait_until_mu(now_mu())

        self._call_camera_rpc()

        sums = [0]
        means = [0.0]
        self.andor_camera_control.readout_ROIs(
            sums,
            means,
            timeout_mu=self.core.get_rtio_counter_mu() + self.core.seconds_to_mu(1.0),
        )
        self.andor_sum.push(sums[0])
        self.andor_mean.push(means[0])
