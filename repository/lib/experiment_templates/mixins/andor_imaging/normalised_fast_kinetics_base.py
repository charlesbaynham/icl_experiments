"""
TODO: Remove duplication in normalised imaging code. Details:

- We have a seperate module for the "base" and the mixins code. We shouldn't
  need this, if we need a base class it should only be used privately within the
  mixin module.
- We mix mixins and "base" classes between the two modules
- The `NormalisedFastKineticsBase` and `NormalisedFastKineticsDoubleTrapBase`
  classes are almost identical, except for the way they set up the ROIs in
  `host_setup`.
- We should be able to separate the concept of "doing clock repumping" from
  "imaging two traps" to avoid code duplication.
- Our inheritance structure is wild. Take `DoubleTrapImagingSpectroscopyRepumpedNormalised` for example: this goes
        `DoubleTrapImagingSpectroscopyRepumpedNormalised` ->
        NormalisedXXODTSpectroscopyFastKineticsMixin + DoubleTrapImagingRepumpedNormalisedBase ->
        NormalisedFastKineticsDoubleTrapRepumpedMixin ->
        NormalisedFastKineticsDoubleTrapBase ->
        AndorImagingBase
    We should be able to simplify this a lot, it's bewildering.
"""

import logging
from typing import List

import numpy as np
from artiq.language import at_mu
from artiq.language import delay
from artiq.language import host_only
from artiq.language import kernel
from artiq.language import now_mu
from artiq.language import portable
from artiq.language import rpc
from ndscan.experiment import FloatChannel
from ndscan.experiment.parameters import FloatParam
from ndscan.experiment.parameters import FloatParamHandle
from ndscan.experiment.parameters import IntParam
from ndscan.experiment.parameters import IntParamHandle
from numpy.typing import NDArray
from pyaion.models import UrukuledBeam

from repository.lib import constants
from repository.lib.experiment_templates.mixins.andor_imaging.imaging_base import (
    ANDOR_FK_E_BG_CORR_DATASET,
)
from repository.lib.experiment_templates.mixins.andor_imaging.imaging_base import (
    ANDOR_FK_E_BG_CORR_ROI_TARGETS_DATASET,
)
from repository.lib.experiment_templates.mixins.andor_imaging.imaging_base import (
    ANDOR_FK_G_BG_CORR_DATASET,
)
from repository.lib.experiment_templates.mixins.andor_imaging.imaging_base import (
    ANDOR_FK_G_BG_CORR_ROI_TARGETS_DATASET,
)
from repository.lib.experiment_templates.mixins.andor_imaging.imaging_base import (
    ANDOR_MONITOR_DATASET,
)
from repository.lib.experiment_templates.mixins.andor_imaging.imaging_base import (
    ANDOR_MONITOR_ROI_TARGETS_DATASET,
)
from repository.lib.experiment_templates.mixins.andor_imaging.imaging_base import (
    ANDOR_MONITOR_SEPARATOR_WIDTH,
)
from repository.lib.experiment_templates.mixins.andor_imaging.imaging_base import (
    AndorImagingBase,
)
from repository.lib.experiment_templates.mixins.andor_imaging.imaging_base import (
    fit_2d_gaussian,
)
from repository.lib.experiment_templates.mixins.clock_spectroscopy import (
    ClockSpectroscopyBase,
)
from repository.lib.fragments.cameras.andor_camera import FastKineticsCameraConfig

logger = logging.getLogger(__name__)

CLOCK_DOWN_BEAM_INFO: UrukuledBeam = constants.URUKULED_BEAMS["clock_down"]
# Full clock-delivery setpoint, resolved host-side (string-keyed dict lookups are
# not permitted inside kernels) for the full-power readout pulse.
CLOCK_DELIVERY_SETPOINT_V: float = constants.SUSERVOED_BEAMS["clock_delivery"].setpoint

# 5x7 pixel bitmaps for the composite monitor frame labels, rows top-to-bottom.
_LABEL_BITMAPS = {
    "G": [
        "01110",
        "10001",
        "10000",
        "10111",
        "10001",
        "10001",
        "01110",
    ],
    "E": [
        "11111",
        "10000",
        "10000",
        "11110",
        "10000",
        "10000",
        "11111",
    ],
}


def _stamp_frame_label(image, letter, a0, b0, value):
    """Draw ``letter`` into ``image`` with its top-left pixel at array index
    (``a0``, ``b0``).

    Bitmap columns run along array axis 0 (rendered horizontally) and rows along
    axis 1 (rendered vertically), matching the composite monitor image.
    """
    for row, bits in enumerate(_LABEL_BITMAPS[letter]):
        for col, bit in enumerate(bits):
            if bit == "1":
                a = a0 + col
                b = b0 + row
                if 0 <= a < image.shape[0] and 0 <= b < image.shape[1]:
                    image[a, b] = value


class NormalisedFKConfig(FastKineticsCameraConfig):
    """
    Camera config for normalised fast kinetics readout of a single trap.

    Supports 2 images per series (ground + excited state), producing 2 grabber ROIs.

    Note that the y heights have the fast kinetics offset subtracted from them, this makes them appear to match up with the andor monitor image.
    """

    num_andor_images = 4
    num_images_per_series = 2
    num_grabber_rois = 2
    num_grabber_readouts = 2
    fast_kinetics_num_shots = 2

    fast_kinetics_height = constants.ANDOR_FAST_KINETICS_HEIGHT
    fast_kinetics_offset = constants.ANDOR_FAST_KINETICS_OFFSET

    def build_fragment(self, x0, y0, x1, y1, excited_shift=0):
        super().build_fragment()

        self.setattr_param(
            "roi_x0",
            IntParam,
            "Grabber ROI x0",
            default=x0,
            min=0,
            max=512,
        )
        self.roi_x0: IntParamHandle
        self.setattr_param(
            "roi_y0",
            IntParam,
            "Grabber ROI y0",
            default=y0 - self.fast_kinetics_offset,
            min=0,
            max=1024,
        )
        self.roi_y0: IntParamHandle
        self.setattr_param(
            "roi_x1",
            IntParam,
            "Grabber ROI x1",
            default=x1,
            min=0,
            max=512,
        )
        self.roi_x1: IntParamHandle
        self.setattr_param(
            "roi_y1",
            IntParam,
            "Grabber ROI y1",
            default=y1 - self.fast_kinetics_offset,
            min=0,
            max=1024,
        )
        self.roi_y1: IntParamHandle

        self.setattr_param(
            "excited_shift",
            IntParam,
            "Excited state ROI shift in pixels",
            default=np.int32(excited_shift),
        )
        self.excited_shift: IntParamHandle

        self.roi_buffer = np.zeros((self.num_grabber_rois, 4), dtype=np.int32)

    @portable
    def get_rois(self):
        height = self.fast_kinetics_height

        x0 = self.roi_x0.get()
        y0_minus_offset = self.roi_y0.get()
        x1 = self.roi_x1.get()
        y1_minus_offset = self.roi_y1.get()

        step = height - self.excited_shift.get()

        self.roi_buffer[0][0] = x0
        self.roi_buffer[0][1] = y0_minus_offset
        self.roi_buffer[0][2] = x1
        self.roi_buffer[0][3] = y1_minus_offset
        self.roi_buffer[1][0] = x0
        self.roi_buffer[1][1] = y0_minus_offset + step
        self.roi_buffer[1][2] = x1
        self.roi_buffer[1][3] = y1_minus_offset + step
        return self.roi_buffer


class NormalisedFKDoubleTrapConfig(FastKineticsCameraConfig):
    """
    Camera config for normalised fast kinetics readout of two traps (forward + backward).

    Supports 2 images per series (ground + excited), 4 grabber ROIs (2 per trap).
    """

    num_andor_images = 4
    num_images_per_series = 2
    num_grabber_rois = 4
    num_grabber_readouts = 2
    fast_kinetics_num_shots = 2

    fast_kinetics_height = constants.ANDOR_FAST_KINETICS_HEIGHT
    fast_kinetics_offset = constants.ANDOR_FAST_KINETICS_OFFSET

    def build_fragment(
        self,
        fwd_x0,
        fwd_y0,
        fwd_x1,
        fwd_y1,
        bwd_x0,
        bwd_y0,
        bwd_x1,
        bwd_y1,
        excited_shift=0,
    ):
        super().build_fragment()

        self.setattr_param(
            "fwd_roi_x0",
            IntParam,
            "Forward trap grabber ROI x0",
            default=fwd_x0,
            min=0,
            max=512,
        )
        self.fwd_roi_x0: IntParamHandle
        self.setattr_param(
            "fwd_roi_y0",
            IntParam,
            "Forward trap grabber ROI y0",
            default=fwd_y0 - self.fast_kinetics_offset,
            min=0,
            max=1024,
        )
        self.fwd_roi_y0: IntParamHandle
        self.setattr_param(
            "fwd_roi_x1",
            IntParam,
            "Forward trap grabber ROI x1",
            default=fwd_x1,
            min=0,
            max=512,
        )
        self.fwd_roi_x1: IntParamHandle
        self.setattr_param(
            "fwd_roi_y1",
            IntParam,
            "Forward trap grabber ROI y1",
            default=fwd_y1 - self.fast_kinetics_offset,
            min=0,
            max=1024,
        )
        self.fwd_roi_y1: IntParamHandle

        self.setattr_param(
            "bwd_roi_x0",
            IntParam,
            "Backward trap grabber ROI x0",
            default=bwd_x0,
            min=0,
            max=512,
        )
        self.bwd_roi_x0: IntParamHandle
        self.setattr_param(
            "bwd_roi_y0",
            IntParam,
            "Backward trap grabber ROI y0",
            default=bwd_y0 - self.fast_kinetics_offset,
            min=0,
            max=1024,
        )
        self.bwd_roi_y0: IntParamHandle
        self.setattr_param(
            "bwd_roi_x1",
            IntParam,
            "Backward trap grabber ROI x1",
            default=bwd_x1,
            min=0,
            max=512,
        )
        self.bwd_roi_x1: IntParamHandle
        self.setattr_param(
            "bwd_roi_y1",
            IntParam,
            "Backward trap grabber ROI y1",
            default=bwd_y1 - self.fast_kinetics_offset,
            min=0,
            max=1024,
        )
        self.bwd_roi_y1: IntParamHandle

        self.setattr_param(
            "excited_shift",
            IntParam,
            "Excited state ROI shift in pixels",
            default=np.int32(excited_shift),
        )
        self.excited_shift: IntParamHandle
        self.roi_buffer = np.zeros((self.num_grabber_rois, 4), dtype=np.int32)

    @portable
    def get_rois(self):
        height = self.fast_kinetics_height
        step = height - self.excited_shift.get()

        fwd_x0 = self.fwd_roi_x0.get()
        fwd_y0_minus_offset = self.fwd_roi_y0.get()
        fwd_x1 = self.fwd_roi_x1.get()
        fwd_y1_minus_offset = self.fwd_roi_y1.get()

        self.roi_buffer[0][0] = fwd_x0
        self.roi_buffer[0][1] = fwd_y0_minus_offset
        self.roi_buffer[0][2] = fwd_x1
        self.roi_buffer[0][3] = fwd_y1_minus_offset
        self.roi_buffer[1][0] = fwd_x0
        self.roi_buffer[1][1] = fwd_y0_minus_offset + step
        self.roi_buffer[1][2] = fwd_x1
        self.roi_buffer[1][3] = fwd_y1_minus_offset + step

        bwd_x0 = self.bwd_roi_x0.get()
        bwd_y0_minus_offset = self.bwd_roi_y0.get()
        bwd_x1 = self.bwd_roi_x1.get()
        bwd_y1_minus_offset = self.bwd_roi_y1.get()

        self.roi_buffer[2][0] = bwd_x0
        self.roi_buffer[2][1] = bwd_y0_minus_offset
        self.roi_buffer[2][2] = bwd_x1
        self.roi_buffer[2][3] = bwd_y1_minus_offset
        self.roi_buffer[3][0] = bwd_x0
        self.roi_buffer[3][1] = bwd_y0_minus_offset + step
        self.roi_buffer[3][2] = bwd_x1
        self.roi_buffer[3][3] = bwd_y1_minus_offset + step
        return self.roi_buffer


class NormalisedFastKineticsBase(AndorImagingBase):
    """
    Implements normalised readout for a :py:class:`~RedMOTWithExperimentBase`
    experiment

    This mixin base uses the Andor camera to two fast kinetics series with two images each and create
    ResultChannels for normalised state readout. The first series contains atoms that starts in (i)
    the ground state, and (ii) the excited state. The second series reproduces the conditions of the first,
    with a long delay to clear out atoms.

    Variant mixins based on this class are expected to reimplement get_andor_camera_config_hook
    to provide a custom config (e.g. with different ROI defaults or FK height/offset) as needed.

    This is a mixin - see the documentation for :mod:`~.red_mot_experiment` for
    details.

    Kernel hooks used (multiple mixins cannot use the same hooks):

    * :meth:`~do_imaging_hook_andor`
    * :meth:`~process_andor_data_hook`
    * :meth:`~update_andor_monitor_hook`
    """

    def get_andor_camera_config_hook(self):
        f = self.setattr_fragment(
            "andor_camera_config",
            NormalisedFKConfig,
            x0=constants.ANDOR_ROI_X0,
            y0=constants.ANDOR_ROI_Y0,
            x1=constants.ANDOR_ROI_X1,
            y1=constants.ANDOR_ROI_Y1,
        )
        self.andor_camera_config: NormalisedFKConfig
        return f

    def build_fragment(self):
        super().build_fragment()

        self.setattr_param(
            "delay_between_imaging_pulses",
            FloatParam,
            "Time between the start of each fluorescence pulse",
            default=3.5e-3,
            unit="ms",
        )
        self.delay_between_imaging_pulses: FloatParamHandle
        # Note the wording of this parameter - it's the time between the starts
        # of the pulses, not the time the end of one and the start of the next
        # one. This interacts non-trivially with the way that the Andor camera
        # clocks out rows of the EMCCD in Fast Kinetics Mode. See the comments
        # in :mod:`~.andor_camera` and the lab book entry from 2024-10-30 for
        # more detail.

        # Force the camera's fast kinetics shot time to match our pulse time
        self.andor_camera_config.bind_param(
            "fast_kinetics_time_between_shots",
            self.delay_between_imaging_pulses,
        )

        self.setattr_param(
            "delay_before_bg_img",
            FloatParam,
            "Delay before bg image series",
            default=400e-3,
            unit="ms",
        )
        self.delay_before_bg_img: FloatParamHandle

        self.fast_kinetics_setup_results()

    def host_setup(self):
        super().host_setup()

        default_rois_ground, default_rois_excited = (
            self._split_bg_corrected_roi_targets(
                self.andor_camera_config.get_rois(),
                self.andor_camera_config.fast_kinetics_height,
            )
        )

        self.set_dataset(
            ANDOR_FK_G_BG_CORR_ROI_TARGETS_DATASET, default_rois_ground, broadcast=True
        )
        self.set_dataset(
            ANDOR_FK_E_BG_CORR_ROI_TARGETS_DATASET, default_rois_excited, broadcast=True
        )
        self.ccb.issue(
            "create_applet",
            "Ground bg corrected",
            f"${{python}} -m custom_artiq_applets.full_img_applet {ANDOR_FK_G_BG_CORR_DATASET} --dataset_prefix 'g_bg_corrected' --rois_dataset {ANDOR_FK_G_BG_CORR_ROI_TARGETS_DATASET}",
        )
        self.ccb.issue(
            "create_applet",
            "Excited bg corrected",
            f"${{python}} -m custom_artiq_applets.full_img_applet {ANDOR_FK_E_BG_CORR_DATASET} --dataset_prefix 'e_bg_corrected' --rois_dataset {ANDOR_FK_E_BG_CORR_ROI_TARGETS_DATASET}",
        )

    def fast_kinetics_setup_results(self):
        self.setattr_result("excitation_fraction", FloatChannel)
        self.setattr_result("atom_number", FloatChannel)

        self.excitation_fraction: FloatChannel
        self.atom_number: FloatChannel

    def setup_gauss_fit_results(self):
        self.amps: List[FloatChannel] = []
        self.x_pos: List[FloatChannel] = []
        self.y_pos: List[FloatChannel] = []
        self.sigmas_x: List[FloatChannel] = []
        self.sigmas_y: List[FloatChannel] = []
        for i in range(
            int(
                self.andor_camera_config.num_grabber_rois
                / self.andor_camera_config.num_grabber_readouts
            )
        ):
            for j in ("ground", "excited"):
                self.amps.append(
                    self.setattr_result(
                        f"amp_{i}_{j}", FloatChannel, display_hints={"priority": -1}
                    )
                )
                self.x_pos.append(
                    self.setattr_result(
                        f"x_pos_{i}_{j}", FloatChannel, display_hints={"priority": -1}
                    )
                )
                self.y_pos.append(
                    self.setattr_result(
                        f"y_pos_{i}_{j}", FloatChannel, display_hints={"priority": -1}
                    )
                )
                self.sigmas_x.append(
                    self.setattr_result(
                        f"sigma_x_{i}_{j}", FloatChannel, display_hints={"priority": -1}
                    )
                )
                self.sigmas_y.append(
                    self.setattr_result(
                        f"sigma_y_{i}_{j}", FloatChannel, display_hints={"priority": -1}
                    )
                )

    @kernel
    def do_imaging_hook_andor(self):
        """
        Hook for the imaging sequence. This hook runs after the spectroscopy
        etc. is completed, and should handle imaging with the Andor camera.
        """
        self.do_imaging_hook_andor_default()

    @kernel
    def do_imaging_hook_andor_default(self):
        """
        Default implementation of the imaging hook. Overrides of
        :meth:`do_imaging_hook_andor` call this by name, since ARTIQ kernels
        do not support ``super()``.
        """
        self.do_first_series()
        t_post_mu = now_mu()
        self.post_first_series()  # call rpc to get images, start next acquisition
        at_mu(t_post_mu)
        delay(self.delay_before_bg_img.get())
        self.pre_second_series()
        self.do_second_series()
        self.post_second_series()  # call rpc to get images

    @kernel
    def do_first_series(self):
        # Image ground state atoms
        t_start_mu = now_mu()
        self.do_first_pulse()

        # Image excited state atoms
        at_mu(t_start_mu)
        delay(self.delay_between_imaging_pulses.get())
        self.do_second_pulse()

    @kernel
    def post_first_series(self):
        """
        eg turn off beams, start acquisition
        """
        self.post_first_series_rpc()

    @rpc
    def post_first_series_rpc(self):
        self.image_store = []  # clear the image store
        self.image_store += self.get_andor_images()
        self.andor_camera_control.start_acquisition()

    @kernel
    def pre_second_series(self):
        """
        eg turn on beams for some time
        must not advance the timeline
        """

    @kernel
    def do_second_series(self):
        # second verse, same as the first
        self.do_first_series()

    @kernel
    def post_second_series(self):
        pass

    @kernel
    def do_first_pulse(self):
        # Normal fluorescence pulse at now_mu() + camera trigger, pre-empted by
        # the time required to shift one Fast Kinetics region + a
        # pre_trigger_delay
        self.do_pulse()

    @kernel
    def do_second_pulse(self):
        self.do_just_a_fluorescence_pulse()

    @kernel
    def do_just_a_fluorescence_pulse(self):
        # Just a fluorescence pulse - the camera has already been triggered and handles its own timings
        self.fluorescence_pulse.do_imaging_pulse(ignore_final_shutters=True)

    @kernel
    def process_grabber_data_hook(self, sums, means):
        atom_number = sums[0] + sums[1] - sums[2] - sums[3]

        if atom_number == 0:
            self.excitation_fraction.push(0.0)
        else:
            self.excitation_fraction.push((sums[1] - sums[3]) / atom_number)

        self.atom_number.push(atom_number)

    @host_only
    def update_andor_monitor_hook(self, images):
        """
        Show a composite of the background-corrected ground and excited state
        images, stacked vertically, instead of the raw first image.

        The monitor applet renders array axis 1 vertically, so a vertical stack
        is a concatenation along axis 1 (``np.hstack``), with a bright separator
        strip between the two frames and an "E" / "G" label stamped into each
        frame's corner. In this codebase axis 1 is the ROI y-axis and is
        *flipped* (see :meth:`~AndorImagingBase.slice_from_roi_params`), so the
        excited frame, which ``np.hstack`` places at the low-index end, is the
        one whose ROI is offset in y by the sub-frame height plus the separator
        width; the ground frame keeps its coordinates.
        """
        ground_corrected = np.int32(images[0]) - np.int32(images[2])
        excited_corrected = np.int32(images[1]) - np.int32(images[3])

        separator_width = ANDOR_MONITOR_SEPARATOR_WIDTH
        label_value = int(max(excited_corrected.max(), ground_corrected.max()))
        separator = np.full(
            (excited_corrected.shape[0], separator_width),
            label_value,
            dtype=np.int32,
        )
        composite = np.hstack([excited_corrected, separator, ground_corrected])

        # Label each frame in its corner: "E" on the excited frame (low-index
        # end), "G" on the ground frame (past the separator).
        frame_height = excited_corrected.shape[1]
        _stamp_frame_label(composite, "E", 3, 3, label_value)
        _stamp_frame_label(
            composite, "G", 3, frame_height + separator_width + 3, label_value
        )

        self.set_dataset(
            ANDOR_MONITOR_DATASET,
            composite,
            broadcast=True,
            persist=False,
            archive=False,
        )

        # Rebuild the monitor ROI targets to line up on the composite. Routed
        # through an overridable method so mixins with dynamically-predicted
        # ROIs (whose positions are only current kernel-side) can supply the
        # live ROIs instead of the stale host-side get_rois() sampled here.
        self._broadcast_monitor_roi_targets()

    @host_only
    def _broadcast_monitor_roi_targets(self):
        """Broadcast the composite monitor ROI targets from the host-side
        ``get_rois()``. Correct for static-config experiments; overridden by
        dynamic-ROI mixins that must source the ROIs kernel-side."""
        self.set_dataset(
            ANDOR_MONITOR_ROI_TARGETS_DATASET,
            self._composite_monitor_roi_targets(
                self.andor_camera_config.get_rois(),
                self.andor_camera_config.fast_kinetics_height,
            ),
            broadcast=True,
        )

    @rpc(flags={"async"})
    def process_andor_image_hook(self, images: np.array):
        super().process_andor_image_hook(images)
        ground_bg_corrected = images[0].astype(int) - images[2].astype(int)
        excited_bg_corrected = images[1].astype(int) - images[3].astype(int)
        self.set_dataset(
            ANDOR_FK_G_BG_CORR_DATASET,
            ground_bg_corrected,
            broadcast=True,
            persist=False,
            archive=False,
        )
        self.set_dataset(
            ANDOR_FK_E_BG_CORR_DATASET,
            excited_bg_corrected,
            broadcast=True,
            persist=False,
            archive=False,
        )

    @host_only
    def do_gauss_fit_hook(self, img_array: np.ndarray):
        ground_bg_corrected = img_array[0].astype(int) - img_array[2].astype(int)
        excited_bg_corrected = img_array[1].astype(int) - img_array[3].astype(int)
        for i in range(
            int(
                self.andor_camera_config.num_grabber_rois
                / self.andor_camera_config.num_grabber_readouts
            )
        ):
            for j, image in enumerate([ground_bg_corrected, excited_bg_corrected]):
                grabber_idx = int(2 * i)

                sliced_image, offsets = self.slice_from_roi_params(
                    image, self.andor_camera_config.get_rois()[grabber_idx]
                )
                popt = fit_2d_gaussian(sliced_image, offsets)
                self.push_gauss_fit_pars(popt, int(2 * i + j))


class NormalisedFastKineticsDoubleTrapBase(AndorImagingBase):
    """
    Implements normalised readout for a :py:class:`~RedMOTWithExperimentBase`
    experiment

    This mixin base uses the Andor camera to two fast kinetics series with two images each and create
    ResultChannels for normalised state readout. The first series contains atoms that starts in (i)
    the ground state, and (ii) the excited state. The second series reproduces the conditions of the first,
    with a long delay to clear out atoms.

    Variant mixins based on this class are expected to reimplement get_andor_camera_config_hook
    to provide a custom config (e.g. with different ROI defaults or FK height/offset) as needed.

    This is a mixin - see the documentation for :mod:`~.red_mot_experiment` for
    details.

    Kernel hooks used (multiple mixins cannot use the same hooks):

    * :meth:`~do_imaging_hook_andor`
    * :meth:`~process_andor_data_hook`
    * :meth:`~update_andor_monitor_hook`
    """

    def get_andor_camera_config_hook(self):
        f = self.setattr_fragment(
            "andor_camera_config",
            NormalisedFKDoubleTrapConfig,
            fwd_x0=constants.ANDOR_ROI_DIPOLE_TRAP_FORWARD_X0,
            fwd_y0=constants.ANDOR_ROI_DIPOLE_TRAP_FORWARD_Y0,
            fwd_x1=constants.ANDOR_ROI_DIPOLE_TRAP_FORWARD_X1,
            fwd_y1=constants.ANDOR_ROI_DIPOLE_TRAP_FORWARD_Y1,
            bwd_x0=constants.ANDOR_ROI_DIPOLE_TRAP_BACKWARD_X0,
            bwd_y0=constants.ANDOR_ROI_DIPOLE_TRAP_BACKWARD_Y0,
            bwd_x1=constants.ANDOR_ROI_DIPOLE_TRAP_BACKWARD_X1,
            bwd_y1=constants.ANDOR_ROI_DIPOLE_TRAP_BACKWARD_Y1,
        )
        self.andor_camera_config: NormalisedFKDoubleTrapConfig
        return f

    def build_fragment(self):
        super().build_fragment()

        self.setattr_param(
            "delay_between_imaging_pulses",
            FloatParam,
            "Time between the start of each fluorescence pulse",
            default=constants.FAST_KINETICS_DELAY_BETWEEN_PULSES,
            unit="ms",
        )
        self.delay_between_imaging_pulses: FloatParamHandle

        self.setattr_param(
            "temporary_delay_between_series",
            FloatParam,
            "Temporary delay between first and second fast kinetics series",
            default=200e-3,
            min=0.0,
            unit="ms",
        )
        self.temporary_delay_between_series: FloatParamHandle

        # Note the wording of this parameter - it's the time between the starts
        # of the pulses, not the time the end of one and the start of the next
        # one. This interacts non-trivially with the way that the Andor camera
        # clocks out rows of the EMCCD in Fast Kinetics Mode. See the comments
        # in :mod:`~.andor_camera` and the lab book entry from 2024-10-30 for
        # more detail.

        # Force the camera's fast kinetics shot time to match our pulse time
        self.andor_camera_config.bind_param(
            "fast_kinetics_time_between_shots",
            self.delay_between_imaging_pulses,
        )

        self.fast_kinetics_setup_results()

    def host_setup(self):
        super().host_setup()

        default_rois_ground, default_rois_excited = (
            self._split_bg_corrected_roi_targets(
                self.andor_camera_config.get_rois(),
                self.andor_camera_config.fast_kinetics_height,
                ground_indices=(0, 2),
                excited_indices=(1, 3),
            )
        )

        self.set_dataset(
            ANDOR_FK_G_BG_CORR_ROI_TARGETS_DATASET, default_rois_ground, broadcast=True
        )
        self.set_dataset(
            ANDOR_FK_E_BG_CORR_ROI_TARGETS_DATASET, default_rois_excited, broadcast=True
        )
        self.ccb.issue(
            "create_applet",
            "Ground bg corrected",
            f"${{python}} -m custom_artiq_applets.full_img_applet {ANDOR_FK_G_BG_CORR_DATASET} --dataset_prefix 'g_bg_corrected' --rois_dataset {ANDOR_FK_G_BG_CORR_ROI_TARGETS_DATASET}",
        )
        self.ccb.issue(
            "create_applet",
            "Excited bg corrected",
            f"${{python}} -m custom_artiq_applets.full_img_applet {ANDOR_FK_E_BG_CORR_DATASET} --dataset_prefix 'e_bg_corrected' --rois_dataset {ANDOR_FK_E_BG_CORR_ROI_TARGETS_DATASET}",
        )

    def fast_kinetics_setup_results(self):
        self.setattr_result("excitation_fraction", FloatChannel)
        self.setattr_result("atom_number", FloatChannel)

        self.excitation_fraction: FloatChannel
        self.atom_number: FloatChannel

    def setup_gauss_fit_results(self):
        self.amps: List[FloatChannel] = []
        self.x_pos: List[FloatChannel] = []
        self.y_pos: List[FloatChannel] = []
        self.sigmas_x: List[FloatChannel] = []
        self.sigmas_y: List[FloatChannel] = []
        for i in range(
            int(
                self.andor_camera_config.num_grabber_rois
                / self.andor_camera_config.num_grabber_readouts
            )
        ):
            for j in ("ground", "excited"):
                self.amps.append(
                    self.setattr_result(
                        f"amp_{i}_{j}", FloatChannel, display_hints={"priority": -1}
                    )
                )
                self.x_pos.append(
                    self.setattr_result(
                        f"x_pos_{i}_{j}", FloatChannel, display_hints={"priority": -1}
                    )
                )
                self.y_pos.append(
                    self.setattr_result(
                        f"y_pos_{i}_{j}", FloatChannel, display_hints={"priority": -1}
                    )
                )
                self.sigmas_x.append(
                    self.setattr_result(
                        f"sigma_x_{i}_{j}", FloatChannel, display_hints={"priority": -1}
                    )
                )
                self.sigmas_y.append(
                    self.setattr_result(
                        f"sigma_y_{i}_{j}", FloatChannel, display_hints={"priority": -1}
                    )
                )

    @kernel
    def do_imaging_hook_andor(self):
        """
        Hook for the imaging sequence. This hook runs after the spectroscopy
        etc. is completed, and should handle imaging with the Andor camera.
        """

        t_start_first_series_mu = now_mu()
        self.do_first_series()
        self.post_first_series()  # call rpc to get images, start next acquisition

        # HACK This was a temporary patch for an experiment we were running, but
        # it's actually better than the bugged code that was previously there so
        # we're leaving it for now. Better to delete it and move over to the new
        # imaging setup entirely.

        at_mu(
            t_start_first_series_mu
            + self.core.seconds_to_mu(self.temporary_delay_between_series.get())
        )
        self.pre_second_series()
        self.do_second_series()
        self.post_second_series()  # call rpc to get images

    @kernel
    def do_first_series(self):
        # Image ground state atoms
        t_start_mu = now_mu()
        self.do_first_pulse()

        # Image excited state atoms
        at_mu(t_start_mu)
        delay(self.delay_between_imaging_pulses.get())
        self.do_second_pulse()

    @kernel
    def post_first_series(self):
        """
        eg turn off beams, start acquisition
        """
        self.post_first_series_rpc()

    @rpc
    def post_first_series_rpc(self):
        self.image_store = []  # clear the image store
        self.image_store += self.get_andor_images()
        self.andor_camera_control.start_acquisition()

    @kernel
    def pre_second_series(self):
        """
        eg turn on beams for some time
        must not advance the timeline
        """

    @kernel
    def do_second_series(self):
        # second verse, same as the first
        self.do_first_series()

    @kernel
    def post_second_series(self):
        pass

    @kernel
    def do_first_pulse(self):
        # Normal fluorescence pulse at now_mu() + camera trigger, pre-empted by
        # the time required to shift one Fast Kinetics region + a
        # pre_trigger_delay
        self.do_pulse()

    @kernel
    def do_second_pulse(self):
        self.do_just_a_fluorescence_pulse()

    @kernel
    def do_just_a_fluorescence_pulse(self):
        # Just a fluorescence pulse - the camera has already been triggered and handles its own timings
        self.fluorescence_pulse.do_imaging_pulse(ignore_final_shutters=True)

    @kernel
    def process_grabber_data_hook(self, sums, means):
        atom_number = sums[0] + sums[1] - sums[2] - sums[3]

        if atom_number == 0:
            self.excitation_fraction.push(0.0)
        else:
            self.excitation_fraction.push((sums[1] - sums[3]) / atom_number)

        self.atom_number.push(atom_number)

    @rpc(flags={"async"})
    def process_andor_image_hook(self, images: NDArray):
        super().process_andor_image_hook(images)
        ground_bg_corrected = images[0].astype(int) - images[2].astype(int)
        excited_bg_corrected = images[1].astype(int) - images[3].astype(int)
        self.set_dataset(
            ANDOR_FK_G_BG_CORR_DATASET,
            ground_bg_corrected,
            broadcast=True,
            persist=False,
            archive=False,
        )
        self.set_dataset(
            ANDOR_FK_E_BG_CORR_DATASET,
            excited_bg_corrected,
            broadcast=True,
            persist=False,
            archive=False,
        )

    @host_only
    def do_gauss_fit_hook(self, img_array: np.ndarray):
        ground_bg_corrected = img_array[0].astype(int) - img_array[2].astype(int)
        excited_bg_corrected = img_array[1].astype(int) - img_array[3].astype(int)
        for i in range(
            int(
                self.andor_camera_config.num_grabber_rois
                / self.andor_camera_config.num_grabber_readouts
            )
        ):
            for j, image in enumerate([ground_bg_corrected, excited_bg_corrected]):
                grabber_idx = int(2 * i)

                sliced_image, offsets = self.slice_from_roi_params(
                    image, self.andor_camera_config.get_rois()[grabber_idx]
                )
                popt = fit_2d_gaussian(sliced_image, offsets)
                self.push_gauss_fit_pars(popt, int(2 * i + j))


class NormalisedFastKineticsRepumpedMixin(NormalisedFastKineticsBase):
    """
    Adds repumping after the first fluorescence pulse to a
    :class:`~.NormalisedFastKineticsBase` experiment.

    This is a mixin for :class:`~.NormalisedFastKineticsBase`.

    Kernel hooks used (multiple mixins cannot use the same hooks):

    * :meth:`~do_first_pulse`
    * :meth:`~do_imaging_hook_andor`
    """

    def build_fragment(self):
        super().build_fragment()

        self.setattr_param(
            "delay_repumps_after_first_pulse",
            FloatParam,
            "Delay after first fluorescence pulse before repumps turn on",
            default=0.01e-3,
            unit="ms",
        )
        self.delay_repumps_after_first_pulse: FloatParamHandle

    @kernel
    def do_first_pulse(self):
        self.do_pulse()
        delay(self.delay_repumps_after_first_pulse.get())
        self.blue_3d_mot.turn_on_repumpers()


class NormalisedFastKineticsClockPulseMixin(
    NormalisedFastKineticsBase, ClockSpectroscopyBase
):
    """
    Adds a clock pi pulse after the first fluorescence pulse to a
    :class:`~.NormalisedFastKineticsBase` experiment, in order to selectively
    bring the excited state in the ground state before imaging.

    This is a mixin for :class:`~.NormalisedFastKineticsBase`.

    Kernel hooks used (multiple mixins cannot use the same hooks):

    * :meth:`~do_first_pulse`
    * :meth:`~do_imaging_hook_andor`
    """

    def build_fragment(self):
        super().build_fragment()

        self.setattr_param(
            "delay_clock_after_first_pulse",
            FloatParam,
            "Delay after first fluorescence pulse before the pi pulse",
            default=0.01e-3,
            unit="ms",
        )
        self.delay_clock_after_first_pulse: FloatParamHandle

        self.setattr_param(
            "imaging_clock_pulse_detuning",
            FloatParam,
            "Detuning for the imaging clock pulse",
            default=0.0,
            unit="kHz",
        )
        self.imaging_clock_pulse_detuning: FloatParamHandle

    @kernel
    def do_first_pulse(self):
        self.do_pulse()
        delay(self.delay_clock_after_first_pulse.get())

        # Drive the delivery servo to full clock power for the readout pulse.
        # A truncated sequence can leave the servo at whatever setpoint its last
        # executed event set (e.g. the low shelving setpoint after a slice-only
        # truncation), so the readout sets full power itself. This makes the
        # readout a full-power, fast (Fourier-broad) DOWN pi identical in speed
        # to the launch/mirror pulses - the M-state selection pulse.
        self.set_clock_delivery_aom(
            freq=self.calculate_clock_delivery_freq(now_mu(), 0.0),
            setpoint_v=CLOCK_DELIVERY_SETPOINT_V,
        )
        delay(constants.CLOCK_DELIVERY_PREEMPT_TIME)

        # Put the OPLL on the free-fall Doppler resonance the falling atoms
        # actually see. Base (non-LMT) consumers have no OPLL to drive, so this
        # is a no-op there; the LMT-corrected mixin overrides it. Called before
        # the switch-DDS write so the OPLL write gets a ladder-like settling
        # margin before the switch opens.
        self.prepare_readout_opll_hook()

        self.clock_down_dds.set(
            frequency=self.clock_switch_frequency_handle.get()
            + self.imaging_clock_pulse_detuning.get()
            + constants.LMT_DOWN_BEAM_SHIFT,
            amplitude=self.clock_switch_amplitude_handle.get(),
        )

        delay(1e-6)

        self.clock_down_dds.sw.on()
        delay(constants.DOWN_CLOCK_BEAM_PI_TIME)
        self.clock_down_dds.sw.off()

    @kernel
    def prepare_readout_opll_hook(self):
        """Set the readout-pulse OPLL frequency, called just before the pulse.

        Default no-op: the plain :class:`ClockSpectroscopyBase` consumers of
        this mixin have no OPLL tracker. The LMT-corrected mixin overrides this
        to add the free-fall gravity Doppler the ladder pulses carry.
        """


class NormalisedFastKineticsDoubleTrapRepumpedMixin(
    NormalisedFastKineticsDoubleTrapBase
):
    """
    Adds repumping after the first fluorescence pulse to a
    :class:`~.NormalisedFastKineticsBase` experiment.

    This is a mixin for :class:`~.NormalisedFastKineticsBase`.

    Kernel hooks used (multiple mixins cannot use the same hooks):

    * :meth:`~do_first_pulse`
    * :meth:`~do_imaging_hook_andor`
    """

    def build_fragment(self):
        super().build_fragment()

        self.setattr_param(
            "delay_repumps_after_first_pulse",
            FloatParam,
            "Delay after first fluorescence pulse before repumps turn on",
            default=0.01e-3,
            unit="ms",
        )
        self.delay_repumps_after_first_pulse: FloatParamHandle

    @kernel
    def do_first_pulse(self):
        self.do_pulse()
        delay(self.delay_repumps_after_first_pulse.get())
        self.blue_3d_mot.turn_on_repumpers()


class NormalisedFastKineticsDoubleTrapClockPulseMixin(
    NormalisedFastKineticsDoubleTrapBase, ClockSpectroscopyBase
):
    """
    Adds a clock pi pulse after the first fluorescence pulse to a
    :class:`~.NormalisedFastKineticsBase` experiment, in order to selectively
    bring the excited state in the ground state before imaging.

    This is a mixin for :class:`~.NormalisedFastKineticsBase`.

    Kernel hooks used (multiple mixins cannot use the same hooks):

    * :meth:`~do_first_pulse`
    * :meth:`~do_imaging_hook_andor`
    """

    def build_fragment(self):
        super().build_fragment()

        self.setattr_param(
            "delay_clock_after_first_pulse",
            FloatParam,
            "Delay after first fluorescence pulse before the pi pulse",
            default=0.01e-3,
            unit="ms",
        )
        self.delay_clock_after_first_pulse: FloatParamHandle

        self.setattr_param(
            "imaging_clock_pulse_detuning",
            FloatParam,
            "Detuning for the imaging clock pulse",
            default=0.0,
            unit="kHz",
        )
        self.imaging_clock_pulse_detuning: FloatParamHandle

    @kernel
    def do_first_pulse(self):
        self.do_pulse()
        delay(self.delay_clock_after_first_pulse.get())
        self.clock_down_dds.set(
            frequency=self.clock_switch_frequency_handle.get()
            + self.imaging_clock_pulse_detuning.get()
            + constants.LMT_DOWN_BEAM_SHIFT,
            amplitude=self.clock_switch_amplitude_handle.get(),
        )

        delay(1e-6)

        # PI PULSE

        self.clock_down_dds.sw.on()
        delay(constants.CLOCK_DOWN_PI_TIME)
        self.clock_down_dds.sw.off()
