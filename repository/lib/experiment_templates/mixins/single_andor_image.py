import logging

from artiq.experiment import kernel
from artiq.experiment import now_mu
from artiq.experiment import rpc
from ndscan.experiment import FloatChannel
from ndscan.experiment import OpaqueChannel
from ndscan.experiment.parameters import BoolParamHandle

from repository.lib.experiment_templates.red_mot_experiment import RedMOTWithExperiment
from repository.lib.fragments.cameras.andor_camera import AndorCameraControl

logger = logging.getLogger(__name__)
DATASET_NAME = "single_andor_image"


class SingleAndorImage(RedMOTWithExperiment):
    """
    Image with a single fluorescence pulse using the Andor camera

    This is a mixin - see the documentation for :mod:`~.red_mot_experiment` for
    details.

    Kernel hooks used (multiple mixins cannot use the same hooks):

    * :meth:`~do_imaging_hook`
    * :meth:`~save_data_hook`
    """

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

        self.setattr_result("andor_sum_slice_x", OpaqueChannel)
        self.setattr_result("andor_sum_slice_y", OpaqueChannel)
        self.setattr_result("andor_image", OpaqueChannel)
        self.andor_sum_slice_x: OpaqueChannel
        self.andor_sum_slice_y: OpaqueChannel
        self.andor_image: OpaqueChannel

        # self.set_dataset(
        #     "single_andor_image",
        #     np.array([[0.0]]),
        #     broadcast=True,
        #     persist=False,
        #     archive=False,
        # )

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
    def do_imaging_hook(self):
        """
        Hook for the imaging sequence. This hook runs after the spectroscopy
        etc. is completed, and should handle imaging with the Andor camera.
        """
        self.do_imaging_hook_andor()

    @kernel
    def do_imaging_hook_andor(self):
        andor_exposure = 2 * self.fluorescence_pulse.fluorescence_pulse_duration.get()

        # Image ground state atoms
        self.do_pulse(andor_exposure)

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
        # do stuff including writing to resultchannel
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

    @kernel
    def save_data_hook(self):
        "Consume all slack and save the photos"

        self.core.wait_until_mu(now_mu())

        if self.use_andor_driver.get():
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
