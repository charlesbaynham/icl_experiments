import abc
import logging
from typing import List

import numpy as np
from artiq.coredevice.core import Core
from artiq.coredevice.grabber import Grabber
from artiq.coredevice.grabber import GrabberTimeoutException
from artiq.language import host_only
from artiq.language import kernel
from artiq.language import parallel
from artiq.language import rpc
from artiq.language.core import delay
from artiq.master.worker_impl import CCB
from ndscan.experiment import FloatChannel
from ndscan.experiment import Fragment
from ndscan.experiment import OpaqueChannel
from ndscan.experiment.fragment import TransitoryError
from ndscan.experiment.parameters import BoolParam
from ndscan.experiment.parameters import BoolParamHandle
from ndscan.experiment.parameters import FloatParam
from ndscan.experiment.parameters import FloatParamHandle
from pyaion.fragments.andor_camera import AndorCameraConfig
from pyaion.fragments.andor_camera import AndorCameraControl
from pyaion.models import AndorHardware
from sipyco.packed_exceptions import GenericRemoteException

from repository.lib import constants
from repository.lib.analysis.gauss_fit_2d import fit_gaussian
from repository.lib.analysis.tof_temp import get_custom_analysis
from repository.lib.experiment_templates.red_mot_experiment import (
    RedMOTWithExperimentBase,
)
from repository.lib.fragments.set_toptica_analog import SetTopticaAnalogFrag
from repository.lib.result_channels import ArchiveOnlyOpaqueChannel

logger = logging.getLogger(__name__)


ANDOR_MONITOR_DATASET = "andor_monitor_image"
ANDOR_DETAILED_MONITOR_DATASETS = "andor_image_{i}"
ANDOR_MONITOR_ROI_TARGETS_DATASET = "andor_monitor_roi_targets"

# Background-corrected ground/excited image datasets and their ROI-overlay
# target datasets, shared by the fast-kinetics imaging modules.
ANDOR_FK_G_BG_CORR_DATASET = "g_bg_corrected"
ANDOR_FK_E_BG_CORR_DATASET = "e_bg_corrected"
ANDOR_FK_G_BG_CORR_ROI_TARGETS_DATASET = "g_bg_corrected_roi_targets"
ANDOR_FK_E_BG_CORR_ROI_TARGETS_DATASET = "e_bg_corrected_roi_targets"

# Width of the bright separator strip drawn between the excited and ground
# sub-frames in the composite monitor image. The excited ROI is offset by this
# plus the sub-frame height when mapping onto the composite.
ANDOR_MONITOR_SEPARATOR_WIDTH = 2


class AndorImagingBase(RedMOTWithExperimentBase, abc.ABC):
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

    image_read_timeout = 15.0
    "Timeout for the ANDOR camera readout - must be longer than sequence"

    @abc.abstractmethod
    def get_andor_camera_config_hook(self) -> AndorCameraConfig:
        """
        Build an Andor camera config object which defines the behaviour of this
        class

        This method should return an AndorCameraConfig object. It might make one
        using setattr_fragment, or it might return one that was built elsewhere.
        For an example implementation, see :class:`~.bg_corrected_andor_image.BGCorrectedAndorImageMixin`.
        """

    def build_fragment(self):
        super().build_fragment()

        self.setattr_device("ccb")
        self.ccb: CCB

        self.setattr_device("grabber0")
        self.grabber0: Grabber

        self.setattr_param_rebind("use_andor_driver", self.andor_camera_control)
        self.use_andor_driver: BoolParamHandle

        self.setattr_param(
            "do_gauss_fit",
            BoolParam,
            "Do a 2D Gaussian fit on the Andor images",
            False,
        )
        self.do_gauss_fit: BoolParamHandle

        self.kernel_invariants = getattr(self, "kernel_invariants", set())
        self.kernel_invariants.add("do_gauss_fit")

        class ImagingDeviceSetup(Fragment):
            """
            define a device_setup to clear out the grabber and empty the image store at the start of the shot
            """

            def build_fragment(self, num_grabber_rois):
                self.setattr_device("grabber0")
                self.grabber0: Grabber

                self.setattr_param(
                    "set_topica_pre_delay",
                    FloatParam,
                    "Toptica setting pre-delay",
                    default=10e-3,
                    unit="ms",
                )
                self.set_topica_pre_delay: FloatParamHandle

                self.setattr_device("core")
                self.core: Core

                self.setattr_fragment("set_toptica_analog", SetTopticaAnalogFrag)
                self.set_toptica_analog: SetTopticaAnalogFrag

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

        self.setattr_fragment(
            "imagingsetup",
            ImagingDeviceSetup,
            self.andor_camera_config.num_grabber_rois,
        )
        self.imagingsetup: ImagingDeviceSetup

    def setup_andor_hook(self):
        self.andor_camera_config = self.get_andor_camera_config_hook()
        self.setup_andor_camera_control_hook()

    def setup_andor_camera_control_hook(self):
        """
        Setup the Andor camera

        This is a method so that children classes can override it
        """
        self.setattr_fragment(
            "andor_camera_control",
            AndorCameraControl,
            camera_config=self.andor_camera_config,
            hardware=self.get_andor_hardware(),
        )
        self.andor_camera_control: AndorCameraControl

        self.hook_setup_andor_results()

    def get_andor_hardware(self) -> AndorHardware:
        """
        Describe how the Andor camera is wired into this lab.

        The device names and shutter timing live here (not in the pyaion
        fragment) because they are facts about our setup. Override in a
        subclass if a different camera/wiring is used. Camera-intrinsic facts
        (sensor height, trigger-enable latency) keep the pyaion defaults.
        """
        return AndorHardware(
            grabber_device="grabber0",
            camera_device="andor_camera",
            ttl_trigger_device="ttl_camera_trigger_andor",
            ttl_shutter_device="ttl_shutter_andor",
            shutter_open_time=constants.ANDOR_CAMERA_SHUTTER_OPEN_TIME,
            sensor_height=constants.ANDOR_SENSOR_HEIGHT,
            trigger_enable_time=constants.ANDOR_CAMERA_TRIGGER_ENABLE_TIME,
        )

    def setup_gauss_fit_results(self):
        self.amps: List[FloatChannel] = []
        self.x_pos: List[FloatChannel] = []
        self.y_pos: List[FloatChannel] = []
        self.sigmas_x: List[FloatChannel] = []
        self.sigmas_y: List[FloatChannel] = []

        for i in range(self.andor_camera_config.num_grabber_rois):
            self.amps.append(
                self.setattr_result(
                    f"amp_{i}", FloatChannel, display_hints={"priority": -1}
                )
            )
            self.x_pos.append(
                self.setattr_result(
                    f"x_pos_{i}", FloatChannel, display_hints={"priority": -1}
                )
            )
            self.y_pos.append(
                self.setattr_result(
                    f"y_pos_{i}", FloatChannel, display_hints={"priority": -1}
                )
            )
            self.sigmas_x.append(
                self.setattr_result(
                    f"sigma_x_{i}", FloatChannel, display_hints={"priority": -1}
                )
            )
            self.sigmas_y.append(
                self.setattr_result(
                    f"sigma_y_{i}", FloatChannel, display_hints={"priority": -1}
                )
            )

    def hook_setup_andor_results(self):
        # Set up result channels for all the Grabber ROIs
        self.andor_sums: List[FloatChannel] = []
        self.andor_means: List[FloatChannel] = []
        self.setup_gauss_fit_results()

        for i in range(
            self.andor_camera_config.num_grabber_rois
            * self.andor_camera_config.num_grabber_readouts
        ):
            sum = self.setattr_result(
                f"andor_sum_{i}", FloatChannel, display_hints={"priority": -1}
            )
            mean = self.setattr_result(
                f"andor_mean_{i}",
                FloatChannel,
                display_hints=(  # Show by default if there's only one ROI
                    {}
                    if (
                        self.andor_camera_config.num_grabber_rois
                        * self.andor_camera_config.num_grabber_readouts
                        == 1
                    )
                    else {"priority": -1}
                ),
            )

            self.andor_sums.append(sum)  # type: ignore
            self.andor_means.append(mean)  # type: ignore

        # Set up result channels for the Andor images
        self.andor_profile_xs: List[OpaqueChannel] = []
        self.andor_profile_ys: List[OpaqueChannel] = []
        self.andor_images: List[OpaqueChannel] = []

        for i in range(self.andor_camera_config.num_andor_images):
            profile_x = self.setattr_result(f"andor_profile_x_{i}", OpaqueChannel)
            profile_y = self.setattr_result(f"andor_profile_y_{i}", OpaqueChannel)
            # Raw frames are archived to HDF5 but not broadcast: a full-frame
            # image per scan point otherwise bloats the master's live dataset
            # dict past sipyco's ~100 MB sync_struct limit and stalls the whole
            # dataset stream. Live viewing uses the separate ANDOR_DETAILED
            # monitor datasets, not this ndscan result channel.
            image = self.setattr_result(f"andor_image_{i}", ArchiveOnlyOpaqueChannel)

            self.andor_profile_xs.append(profile_x)  # type: ignore
            self.andor_profile_ys.append(profile_y)  # type: ignore
            self.andor_images.append(image)  # type: ignore

    @staticmethod
    def _split_bg_corrected_roi_targets(
        rois, fast_kinetics_height, ground_indices=(0,), excited_indices=(1,)
    ):
        """Map a get_rois() buffer to (ground_targets, excited_targets) lists
        for the bg-corrected applets.

        The excited ROIs are shifted up by the fast-kinetics height so they land
        in the excited sub-frame's pixel coordinates (the applet shows each
        fast-kinetics sub-frame separately). ``ground_indices`` /
        ``excited_indices`` select the signal ROIs per trap (one pair for a
        single trap, two pairs for a double trap).
        """
        ground = [list(rois[i]) for i in ground_indices]
        excited = [list(rois[i]) for i in excited_indices]
        for roi in excited:
            roi[1] -= fast_kinetics_height
            roi[3] -= fast_kinetics_height
        return ground, excited

    @staticmethod
    def _composite_monitor_roi_targets(rois, fast_kinetics_height):
        """Map a get_rois() buffer to the two ROI targets for the composite
        monitor image (``[excited_target, ground_target]``).

        The composite stacks the excited sub-frame (low index) above a
        ``ANDOR_MONITOR_SEPARATOR_WIDTH``-wide separator and the ground
        sub-frame. Because the applet renders array axis 1 flipped, the excited
        ROI is shifted up in y by the sub-frame height plus the separator width
        while the ground ROI keeps its sub-frame coordinates.

        This must be fed ROIs sampled at the same instant as the dedicated
        ground/excited applet targets: for dynamically-predicted ROIs those
        positions are only current kernel-side, so pass the ``get_rois()``
        result from a kernel hook rather than sampling on the host.
        """
        ground, excited = AndorImagingBase._split_bg_corrected_roi_targets(
            rois, fast_kinetics_height
        )
        y_offset = fast_kinetics_height + ANDOR_MONITOR_SEPARATOR_WIDTH
        excited[0][1] += y_offset
        excited[0][3] += y_offset
        return [excited[0], ground[0]]

    def host_setup(self):
        super().host_setup()
        if self.use_andor_driver.get():
            monitor_rois = np.array(self.get_monitor_rois()).tolist()
            self.set_dataset(
                ANDOR_MONITOR_ROI_TARGETS_DATASET, monitor_rois, broadcast=True
            )
            self.ccb.issue(
                "create_applet",
                "Andor monitor image",
                f"${{python}} -m custom_artiq_applets.full_img_applet {ANDOR_MONITOR_DATASET} --rois_dataset {ANDOR_MONITOR_ROI_TARGETS_DATASET} --dataset_prefix 'andor_monitor'",
            )

            # Also make an applet for every image. Don't include the ROIs on
            # here because they might vary per image, and we would have to deal
            # with fast kinetics offsets (if fast kinetics is being used). This
            # is very possible, but the only place this matters at the moment is
            # in normalised readout, and that already shows ROIs in the ground /
            # excited state images.
            for i in range(self.andor_camera_config.num_andor_images):
                dataset_name = ANDOR_DETAILED_MONITOR_DATASETS.format(i=i)
                self.ccb.issue(
                    "create_applet",
                    f"Andor image {i}",
                    f"${{python}} -m custom_artiq_applets.full_img_applet {dataset_name} --dataset_prefix 'andor_img_{i}'",
                )
        self.image_store = []

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
        if self.imagingsetup.set_toptica_analog.freq_step.get() != 0.0:
            delay(-self.imagingsetup.set_topica_pre_delay.get())
            self.imagingsetup.set_toptica_analog.step_freq()
            delay(
                self.imagingsetup.set_topica_pre_delay.get()
                + constants.DELAY_BETWEEN_RTIO_EVENTS
            )
        with parallel:
            self.andor_camera_control.trigger(
                exposure=self.fluorescence_pulse.fluorescence_pulse_duration.get(),
                control_shutter=False,
            )
            if with_light:
                self.fluorescence_pulse.do_imaging_pulse(ignore_final_shutters=True)
        if self.imagingsetup.set_toptica_analog.freq_step.get() != 0.0:
            delay(
                constants.DELAY_BETWEEN_RTIO_EVENTS
            )  # to avoid collision with turn_off_beams in do_imaging_pulse
            self.imagingsetup.set_toptica_analog.reset_freq()
            delay(
                constants.DELAY_BETWEEN_RTIO_EVENTS
            )  # to avoid collision with next event, e.g. MOT field setting in BGCorrectedAndorImageMixin

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
        if n_stored_images != self.andor_camera_config.num_andor_images:
            # raising as transitory error because we believe this mostly likely happens due to timing jitter and we want ndscan to try again
            self.image_store = []
            logger.error(
                "Expected %d images but got %d",
                self.andor_camera_config.num_andor_images,
                n_stored_images,
            )
            raise TransitoryError(
                f"Expected {self.andor_camera_config.num_andor_images} images but got {n_stored_images}"
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
            num_images=self.andor_camera_config.num_images_per_series,
            timeout=self.image_read_timeout,
        )

        return imgs_array.tolist()

    @host_only
    @staticmethod
    def get_projections(img):
        profile_x = np.sum(img, axis=1)
        profile_y = np.sum(img, axis=0)
        return profile_x, profile_y

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

    @host_only
    def get_monitor_rois(self):
        """
        Get the default ROIs for the Andor monitors
        """
        default_rois = [self.andor_camera_config.get_rois()[0]]
        return default_rois

    @kernel
    def save_andor_data_hook(self):
        """
        Consume all slack and save the photos
        """
        if self.use_andor_driver.get():
            self._call_camera_rpc()
        self.get_grabber_data()

    @kernel
    def after_save_andor_data_hook(self):
        pass

    @kernel
    def get_grabber_data(self):
        # Arrays to hold all the ROIs
        sums = (
            [0]
            * self.andor_camera_config.num_grabber_rois
            * self.andor_camera_config.num_grabber_readouts
        )
        means = (
            [0.0]
            * self.andor_camera_config.num_grabber_rois
            * self.andor_camera_config.num_grabber_readouts
        )

        for i in range(self.andor_camera_config.num_grabber_readouts):
            # Arrays to hold the ROIs from this readout
            s = [0] * self.andor_camera_config.num_grabber_rois
            m = [0.0] * self.andor_camera_config.num_grabber_rois

            self.andor_camera_control.readout_ROIs(
                s,
                m,
                timeout_mu=self.core.get_rtio_counter_mu()
                + self.core.seconds_to_mu(1.0),
            )

            # Copy ROI data from temporary arrays into main array
            for j in range(self.andor_camera_config.num_grabber_rois):
                idx = i * self.andor_camera_config.num_grabber_rois + j

                sums[idx] = s[j]
                means[idx] = m[j]

        for i in range(
            self.andor_camera_config.num_grabber_rois
            * self.andor_camera_config.num_grabber_readouts
        ):
            self.andor_sums[i].push(sums[i])
            self.andor_means[i].push(means[i])

        self.process_grabber_data_hook(sums, means)

    @abc.abstractmethod
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
            andor_profile_x,
            andor_profile_y,
            andor_image,
            img_array,
        ) in zip(
            self.andor_profile_xs,
            self.andor_profile_ys,
            self.andor_images,
            imgs_array,
        ):
            if self.use_andor_driver.get():
                profile_x, profile_y = AndorImagingBase.get_projections(img_array)

                # Save space by converting these to int32s instead of int64s
                profile_x = profile_x.astype(np.int32)
                profile_y = profile_y.astype(np.int32)
                img_array = img_array.astype(np.int32)

                # Write them to the result channels
                andor_profile_x.push(profile_x)
                andor_profile_y.push(profile_y)

                # Save them to pass to the monitor

                # Save raw data if requested
                if self.andor_camera_control.save_raw_andor_image.get():
                    andor_image.push(img_array)
                else:
                    andor_image.push([])
            else:
                # We must always push something to ResultChannels, so push something empty
                andor_profile_x.push([])
                andor_profile_y.push([])
                andor_image.push([])

        if self.do_gauss_fit.get():
            logger.debug("Doing gauss fit")
            self.do_gauss_fit_hook(imgs_array)
        else:
            logger.debug("Not doing gauss fit")
            for i in range(len(self.amps)):
                self.push_gauss_fit_pars([np.nan] * 5, i)

    @host_only
    def do_gauss_fit_hook(self, imgs_array):
        for img_array in imgs_array:
            self.fit_from_grabber_rois(img_array)

    @host_only
    @staticmethod
    def slice_from_roi_params(img, roi):
        x0, y0, x1, y1 = roi
        width, height = img.shape

        logger.debug(f"Image shape: {width}, {height}")
        logger.debug(f"ROI: {x0}, {x1}, {y0}, {y1}")

        return img[x0:x1, height - y0 : height - y1 : -1], (x0, y0)

    @host_only
    def fit_from_grabber_rois(self, image):
        rois = self.andor_camera_config.get_rois()
        i = 0
        for roi in rois:
            sliced_image, offsets = self.slice_from_roi_params(image, roi)
            popt = fit_2d_gaussian(sliced_image, offsets)
            self.push_gauss_fit_pars(popt, i)
            i += 1

    @host_only
    def push_gauss_fit_pars(self, pars, i):
        self.amps[i].push(pars[0])
        self.x_pos[i].push(pars[1])
        self.y_pos[i].push(pars[2])
        self.sigmas_x[i].push(pars[3])
        self.sigmas_y[i].push(pars[4])

    def get_default_analyses(self):
        default_analyses = super().get_default_analyses()
        if self.do_gauss_fit.get():
            for name, result in [
                ("T_x", self.sigmas_x[0]),
                ("T_y", self.sigmas_y[0]),
            ]:
                default_analyses += get_custom_analysis(
                    self.expansion_time,
                    result,
                    {
                        "T": name,
                        "fit_xs": f"fit_t_{name}",
                        "fit_ys": f"fit_sigma_{name}",
                    },
                    [
                        FloatChannel(name, f"Fitted {name}", unit="K", scale=1),
                        OpaqueChannel(f"fit_t_{name}"),
                        OpaqueChannel(f"fit_sigma_{name}"),
                    ],
                )  # type: ignore
        return default_analyses


@host_only
def fit_2d_gaussian(image, offsets=(0, 0)):
    """
    Fit a 2D Gaussian to an image
    """
    try:
        popt, _ = fit_gaussian(
            image[:, ::-1], estimator="1d", fitter="curve_fit", method="trf"
        )
    except RuntimeError as e:
        logger.warning("Runtime error in 2d gauss fit, pushing empty")
        logger.warning(e)
        popt = [np.nan] * 5
    except ValueError as e:
        logger.warning("Value error in 2d gauss fit, pushing empty")
        logger.warning(e)
        popt = [np.nan] * 5
    A = popt[0]
    pos_x = popt[1] + offsets[0]
    pos_y = popt[2] + offsets[1]
    sigma_x = popt[3]
    sigma_y = popt[4]
    return A, pos_x, pos_y, sigma_x, sigma_y
