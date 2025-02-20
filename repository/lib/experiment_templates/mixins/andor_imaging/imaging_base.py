import abc
import logging
from typing import List

import numpy as np
from artiq.coredevice.core import Core
from artiq.coredevice.grabber import Grabber
from artiq.coredevice.grabber import GrabberTimeoutException
from artiq.experiment import host_only
from artiq.experiment import kernel
from artiq.experiment import rpc
from artiq.language import parallel
from artiq.language.core import delay
from artiq.master.worker_impl import CCB
from ndscan.experiment import FloatChannel
from ndscan.experiment import Fragment
from ndscan.experiment import OpaqueChannel
from ndscan.experiment.parameters import FloatParam
from ndscan.experiment.parameters import FloatParamHandle
from ndscan.experiment.fragment import TransitoryError
from ndscan.experiment.parameters import BoolParamHandle
from sipyco.packed_exceptions import GenericRemoteException

from repository.lib import constants
from repository.lib.experiment_templates.red_mot_experiment import RedMOTWithExperiment
from repository.lib.fragments.cameras.andor_camera import AndorCameraControl
from repository.lib.fragments.set_toptica_analog import SetTopticaAnalogFrag

logger = logging.getLogger(__name__)


ANDOR_MONITOR_DATASET = "andor_monitor_image"
ANDOR_DETAILED_MONITOR_DATASETS = "andor_image_{i}"


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
    * :meth:`~start_of_red_broadband_hook`
    * :meth:`~save_grabber_data_hook`
    """

    num_andor_images = 1
    "How many images will the Andor driver read out"
    num_images_per_series = 1
    "How many images will the Andor driver read out in each series"
    num_grabber_rois = 1
    "How many ROIs in each image for the Grabber"
    num_grabber_readouts = 1
    "How many images will the Grabber read out"

    keep_andor_shutter_closed = False

    def build_fragment(self):
        super().build_fragment()

        self.setattr_device("ccb")
        self.ccb: CCB

        self.setattr_device("grabber0")
        self.grabber0: Grabber

        self.setattr_param_rebind("use_andor_driver", self.andor_camera_control)
        self.use_andor_driver: BoolParamHandle

        self.setattr_fragment("set_toptica_analog", SetTopticaAnalogFrag)
        self.set_toptica_analog: SetTopticaAnalogFrag

        self.setattr_param("set_topica_pre_delay", FloatParam, "Toptica setting pre-delay", default=0.0, unit="ms")
        self.set_topica_pre_delay: FloatParamHandle

        self.kernel_invariants = getattr(self, "kernel_invariants", set())
        self.kernel_invariants.add("num_andor_images")
        self.kernel_invariants.add("num_grabber_rois")
        self.kernel_invariants.add("num_grabber_readouts")

        class ImagingDeviceSetup(Fragment):
            """
            define a device_setup to clear out the grabber and empty the image store at the start of the shot
            """

            def build_fragment(self, num_grabber_rois):
                self.setattr_device("grabber0")
                self.grabber0: Grabber

                self.setattr_device("core")
                self.core: Core

                self.num_grabber_rois = num_grabber_rois

            @kernel
            def device_setup(self):
                self.device_setup_subfragments()
                self.core.break_realtime()

                grabber_clearout = [0] * self.num_grabber_rois

                while True:
                    try:
                        self.grabber0.input_mu(
                            grabber_clearout,
                            timeout_mu=self.core.get_rtio_counter_mu()
                            + self.core.ref_multiplier * 10,
                        )
                        logger.error("Found a leftover grabber image")
                        delay(1e-3)
                    except GrabberTimeoutException:
                        break

        self.setattr_fragment("imagingsetup", ImagingDeviceSetup, self.num_grabber_rois)

    def hook_setup_andor(self):
        """
        Setup the Andor camera

        This is a method so that children classes can override it
        """
        self.setattr_fragment(
            "andor_camera_control",
            AndorCameraControl,
            roi_defaults=[
                [
                    constants.ANDOR_ROI_X0,
                    constants.ANDOR_ROI_Y0,
                    constants.ANDOR_ROI_X1,
                    constants.ANDOR_ROI_Y1,
                ]
            ]
            * self.num_grabber_rois,
        )
        self.andor_camera_control: AndorCameraControl
        self.andor_camera_control.keep_andor_shutter_closed = (
            self.keep_andor_shutter_closed
        )

        self.hook_setup_andor_results()

    def hook_setup_andor_results(self):
        # Set up result channels for all the Grabber ROIs
        self.andor_sums: List[FloatChannel] = []
        self.andor_means: List[FloatChannel] = []

        for i in range(self.num_grabber_rois * self.num_grabber_readouts):
            sum = self.setattr_result(
                f"andor_sum_{i}", FloatChannel, display_hints={"priority": -1}
            )
            mean = self.setattr_result(
                f"andor_mean_{i}",
                FloatChannel,
                display_hints=(  # Show by default if there's only one ROI
                    {}
                    if (self.num_grabber_rois * self.num_grabber_readouts == 1)
                    else {"priority": -1}
                ),
            )

            self.andor_sums.append(sum)
            self.andor_means.append(mean)

        # Set up result channels for the Andor images
        self.andor_sum_slice_xs: List[OpaqueChannel] = []
        self.andor_sum_slice_ys: List[OpaqueChannel] = []
        self.andor_images: List[OpaqueChannel] = []

        for i in range(self.num_andor_images):
            slice_x = self.setattr_result(f"andor_sum_slice_x_{i}", OpaqueChannel)
            slice_y = self.setattr_result(f"andor_sum_slice_y_{i}", OpaqueChannel)
            image = self.setattr_result(f"andor_image_{i}", OpaqueChannel)

            self.andor_sum_slice_xs.append(slice_x)
            self.andor_sum_slice_ys.append(slice_y)
            self.andor_images.append(image)

    def host_setup(self):
        if self.use_andor_driver.get():
            self.ccb.issue(
                "create_applet",
                "Andor monitor image",
                f"${{python}} -m custom_artiq_applets.full_img_applet {ANDOR_MONITOR_DATASET}",
            )

            for i in range(self.num_andor_images):
                dataset_name = ANDOR_DETAILED_MONITOR_DATASETS.format(i=i)
                self.ccb.issue(
                    "create_applet",
                    f"Andor image {i}",
                    f"${{python}} -m custom_artiq_applets.full_img_applet {dataset_name}",
                )
        self.image_store = []
        super().host_setup()

    @kernel
    def start_of_red_broadband_hook(self):
        self.start_of_red_broadband_hook_imaging_base()

    @kernel
    def start_of_red_broadband_hook_imaging_base(self):
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
        delay(-self.set_topica_pre_delay.get()*1e-3)
        self.set_toptica_analog.step_freq(self.set_toptica_analog.freq_step.get())
        delay(self.set_topica_pre_delay.get()*1e-3)
        with parallel:
            self.andor_camera_control.trigger(
                exposure=self.fluorescence_pulse.fluorescence_pulse_duration.get(),
                control_shutter=False,
            )
            if with_light:
                self.fluorescence_pulse.do_imaging_pulse(ignore_final_shutters=True)
        self.set_toptica_analog.step_freq(0.0)

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

    @rpc  # this isn't async any more because the ndscan "try again" doesn't work with async rpcs
    def _call_camera_rpc(self):
        # Get new images and add them to any images we got earlier
        try:
            self.image_store += self.get_andor_images()
        except GenericRemoteException as e:
            logger.error("Andor camera error: %s", e)
            # raising as transitory error because we believe this mostly likely happens due to timing jitter and we want ndscan to try again
            raise TransitoryError(f"Andor camera error: {e}")
        n_stored_images = len(self.image_store)
        if n_stored_images != self.num_andor_images:
            # raising as transitory error because we believe this mostly likely happens due to timing jitter and we want ndscan to try again
            self.image_store = []
            logger.error(
                "Expected %d images but got %d", self.num_andor_images, n_stored_images
            )
            raise TransitoryError(
                f"Expected {self.num_andor_images} images but got {n_stored_images}"
            )
        images_array = np.array(self.image_store)
        # Update detailed images
        for i, image in enumerate(images_array):
            dataset_name = ANDOR_DETAILED_MONITOR_DATASETS.format(i=i)
            self.set_dataset(
                dataset_name,
                image,
                broadcast=True,
                persist=False,
                archive=False,
            )

        # Update the main monitor
        self.update_andor_monitor_hook(images_array)
        # Do any other processing
        self.process_andor_image_hook(images_array)
        self.image_store = []

    @host_only
    def get_andor_images(self):
        # Readout and store the andor images
        imgs_array = self.andor_camera_control.readout_all_new_images(
            num_images=self.num_images_per_series
        )

        return imgs_array.tolist()

    @host_only
    @staticmethod
    def slice_image(img):
        sum_slice_x = np.sum(img, axis=1)
        sum_slice_y = np.sum(img, axis=0)
        return sum_slice_x, sum_slice_y

    @host_only
    def update_andor_monitor_hook(self, images):
        """
        Update the andor monitor with an appropriate image

        By default, AndorImagingBase will plot the first image in the monitor.
        Override this hook to select a different image.
        """
        self.set_dataset(
            ANDOR_MONITOR_DATASET,
            images[0],
            broadcast=True,
            persist=False,
            archive=False,
        )

    @kernel
    def save_andor_data_hook(self):
        """
        Consume all slack and save the photos
        """
        if self.use_andor_driver.get():
            self._call_camera_rpc()
        self.get_grabber_data()

    @kernel
    def get_grabber_data(self):
        # Arrays to hold all the ROIs
        sums = [0] * self.num_grabber_rois * self.num_grabber_readouts
        means = [0.0] * self.num_grabber_rois * self.num_grabber_readouts

        for i in range(self.num_grabber_readouts):
            # Arrays to hold the ROIs from this readout
            s = [0] * self.num_grabber_rois
            m = [0.0] * self.num_grabber_rois

            self.andor_camera_control.readout_ROIs(
                s,
                m,
                timeout_mu=self.core.get_rtio_counter_mu()
                + self.core.seconds_to_mu(1.0),
            )

            # Copy ROI data from temporary arrays into main array
            for j in range(self.num_grabber_rois):
                idx = i * self.num_grabber_rois + j

                sums[idx] = s[j]
                means[idx] = m[j]

        for i in range(self.num_grabber_rois * self.num_grabber_readouts):
            self.andor_sums[i].push(sums[i])
            self.andor_means[i].push(means[i])

        self.process_grabber_data_hook(sums, means)

    @kernel
    def process_grabber_data_hook(self, sums, means):
        """
        Process the Grabber data

        This is a hook that can be overridden by subclasses to e.g. do background subtraction using the andor datasets
        """

    @rpc(flags={"async"})
    def process_andor_image_hook(self, imgs_array):
        """
        Hook to process the Andor image.
        This method is intended to be overridden by subclasses to implement custom
        processing of the Andor images after they have been read out.
        """
        for (
            andor_sum_slice_x,
            andor_sum_slice_y,
            andor_image,
            img_array,
        ) in zip(
            self.andor_sum_slice_xs,
            self.andor_sum_slice_ys,
            self.andor_images,
            imgs_array,
        ):
            if self.use_andor_driver.get():
                sum_slice_x, sum_slice_y = AndorImagingBase.slice_image(img_array)

                # Write them to the result channels
                andor_sum_slice_x.push(sum_slice_x)
                andor_sum_slice_y.push(sum_slice_y)

                # Save them to pass to the monitor

                # Save raw data if requested
                if self.andor_camera_control.save_raw_andor_image.get():
                    andor_image.push(img_array)
                else:
                    andor_image.push([])
            else:
                # We must always push something to ResultChannels, so push something empty
                andor_sum_slice_x.push([])
                andor_sum_slice_y.push([])
                andor_image.push([])
