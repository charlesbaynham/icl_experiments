from ndscan.experiment import FloatChannel
from ndscan.experiment import OpaqueChannel
from typing import List
import abc
import logging

import numpy as np
from artiq.experiment import kernel, host_only
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

    num_andor_images = 1

    def build_fragment(self):
        super().build_fragment()

        self.setattr_device("ccb")

        self.setattr_param_rebind("use_andor_driver", self.andor_camera_control)
        self.use_andor_driver: BoolParamHandle

    def hook_setup_andor(self):
        """
        Setup the Andor camera

        This is a method so that children classes can override it
        """
        self.setattr_fragment("andor_camera_control", AndorCameraControl)
        self.andor_camera_control: AndorCameraControl

        # Set up result channels for all the images
        self.andor_sums: List[FloatChannel] = []
        self.andor_means: List[FloatChannel] = []
        self.andor_sum_slice_xs: List[OpaqueChannel] = []
        self.andor_sum_slice_ys: List[OpaqueChannel] = []
        self.andor_images: List[OpaqueChannel] = []

        for i in self.num_andor_images:
            sum = self.setattr_result(
                f"andor_sum_{i}", FloatChannel, display_hints={"priority": -1}
            )
            mean = self.setattr_result(f"andor_mean_{i}", FloatChannel)
            slice_x = self.setattr_result(f"andor_sum_slice_x_{i}", OpaqueChannel)
            slice_y = self.setattr_result(f"andor_sum_slice_y_{i}", OpaqueChannel)
            image = self.setattr_result(f"andor_image_{i}", OpaqueChannel)

            self.andor_sums.append(sum)
            self.andor_means.append(mean)
            self.andor_sum_slice_xs.append(slice_x)
            self.andor_sum_slice_ys.append(slice_y)
            self.andor_images.append(image)

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
    def do_pulse(self, with_light=True):
        """
        Default implementation of a fluorescence pulse, available for use by
        mixins (but not used by default).
        """
        with parallel:
            self.andor_camera_control.trigger(
                exposure=self.fluorescence_pulse.fluorescence_pulse_duration.get(),
                control_shutter=False,
            )
            if with_light:
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
        # Readout and store the andor images
        for (
            andor_sum_slice_x,
            andor_sum_slice_y,
            andor_image,
        ) in zip(
            self.andor_sum_slice_xs,
            self.andor_sum_slice_ys,
            self.andor_images,
        ):
            if self.use_andor_driver.get():
                # Read out the images
                img_array = self.andor_camera_control.readout_image()
                sum_slice_x, sum_slice_y = self.slice_image(img_array)

                # Write them to the result channels
                andor_sum_slice_x.push(sum_slice_x)
                andor_sum_slice_y.push(sum_slice_y)

                if self.andor_camera_control.save_raw_andor_image.get():
                    andor_image.push(img_array)
                else:
                    andor_image.push([])
            else:
                # We must always push something to ResultChannels, so push something empty
                andor_sum_slice_x.push([])
                andor_sum_slice_y.push([])
                andor_image.push([])

    @host_only
    def slice_image(self, img):
        sum_slice_x = np.sum(img, axis=1)
        sum_slice_y = np.sum(img, axis=0)
        return sum_slice_x, sum_slice_y

    @host_only
    def update_andor_monitor_hook(self):
        """
        Update the andor monitor with an appropriate image

        Override this hook to select a different image. AndorImagingBase will
        create `num_andor_images`  ResultChannels containing the Andor images,
        so you can use these. NDScan supports a `get_last` method on
        ResultChannels sinks so you can use this: see the example below which
        shows the first image by default.
        """
        try:
            img_array = self.andor_images[0].sink.get_last()
        except AttributeError:
            img_array = [[0.0]]

        if img_array is None:
            img_array = [[0.0]]

        self.set_dataset(
            DATASET_NAME,
            img_array,
            broadcast=True,
            persist=False,
            archive=False,
        )

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
