"""
Dynamic-ROI single-image fast-kinetics imaging.

Combines the two halves of the LMT readout that until now lived apart:

* ROI *positions* come from the recorded pulse-intent trajectory, exactly as in
  :mod:`~.lmt_compensated_normalised_imaging` — the kernel RPCs the intent
  stream to the host predictor and the grabber ROIs are reprogrammed to track
  the two interferometer ports.
* ROI *background* is spatial — each port's signal box is flanked by background
  boxes in the same frame, area-scaled and subtracted, as in
  :mod:`~.single_image_normalised_fast_kinetics_base`.

Spatial background removes the second (temporal) fast-kinetics series entirely,
and with it the ~400 ms clear-out delay per shot. It also removes the offset
that subtracting a weak atom signal against a separate background image
produced (lab book 2026-03-31 / 2026-04-02), which is why the static readouts
moved to it first.

Six grabber ROIs, laid out to match the static single-image configs so the
existing applet index sets work::

    Excited port (second fast-kinetics image):
        +----------+----------+----------+
        |    3     |    1     |    5     |
        +----------+----------+----------+

    Ground port (first fast-kinetics image):
        +----------+----------+----------+
        |    2     |    0     |    4     |
        +----------+----------+----------+
"""

import logging

import numpy as np
from artiq.language import TArray
from artiq.language import TInt32
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
from pyaion.fragments.andor_camera import AndorCameraConfig

from repository.lib import constants
from repository.lib.experiment_templates.mixins.andor_imaging.imaging_base import (
    ANDOR_FK_E_BG_CORR_ROI_TARGETS_DATASET,
)
from repository.lib.experiment_templates.mixins.andor_imaging.imaging_base import (
    ANDOR_FK_G_BG_CORR_ROI_TARGETS_DATASET,
)
from repository.lib.experiment_templates.mixins.andor_imaging.imaging_base import (
    ANDOR_MONITOR_ROI_TARGETS_DATASET,
)
from repository.lib.experiment_templates.mixins.andor_imaging.lmt_compensated_normalised_imaging import (
    LMTCompensatedCameraConfig,
)
from repository.lib.experiment_templates.mixins.andor_imaging.normalised_fast_kinetics_base import (
    CLOCK_DELIVERY_SETPOINT_V,
)
from repository.lib.experiment_templates.mixins.andor_imaging.normalised_fast_kinetics_base import (
    READOUT_BEAM_SIGN,
)
from repository.lib.experiment_templates.mixins.andor_imaging.normalised_fast_kinetics_base import (
    READOUT_START_OPLL_OFFSET,
)
from repository.lib.experiment_templates.mixins.andor_imaging.roi_blocks import (
    background_corrected_counts,
)
from repository.lib.experiment_templates.mixins.andor_imaging.roi_blocks import (
    clamp_roi_in_place,
)
from repository.lib.experiment_templates.mixins.andor_imaging.roi_blocks import (
    collapse_roi_in_place,
)
from repository.lib.experiment_templates.mixins.andor_imaging.roi_blocks import (
    fill_signal_bg_roi_row,
)
from repository.lib.experiment_templates.mixins.andor_imaging.roi_blocks import (
    rois_intersect,
)
from repository.lib.experiment_templates.mixins.andor_imaging.single_image_normalised_fast_kinetics_base import (
    RepumpingWith679Mixin,
)
from repository.lib.experiment_templates.mixins.andor_imaging.single_image_normalised_fast_kinetics_base import (
    SingleImageNormalisedBase,
)
from repository.lib.experiment_templates.mixins.clock_spectroscopy import (
    ClockSpectroscopyBase,
)

logger = logging.getLogger(__name__)

# ROI indices, matching the static single-image layout.
GND_SIGNAL_ROI = 0
EXC_SIGNAL_ROI = 1
GND_BG_LEFT_ROI = 2
EXC_BG_LEFT_ROI = 3
GND_BG_RIGHT_ROI = 4
EXC_BG_RIGHT_ROI = 5

NUM_SINGLE_IMAGE_DYNAMIC_ROIS = 6


# %% Camera config


class LMTCompensatedSingleImageCameraConfig(LMTCompensatedCameraConfig):
    """
    Predicted-position ROIs with same-frame flanking backgrounds.

    Inherits the intent-stream predictor
    (:meth:`~.LMTCompensatedCameraConfig.calculate_atom_positions`) unchanged and
    only replaces the layout: six ROIs instead of two, and one fast-kinetics
    series instead of two, because the background is now spatial.
    """

    num_andor_images = 2
    num_images_per_series = 2
    num_grabber_rois = NUM_SINGLE_IMAGE_DYNAMIC_ROIS
    num_grabber_readouts = 1
    fast_kinetics_num_shots = 2

    def build_fragment(self):
        super().build_fragment()

        self.setattr_param(
            "bg_width",
            IntParam,
            "Background ROI width (pixels)",
            default=constants.ANDOR_SINGLE_FAST_KINETICS_BACKGROUND_ROI_WIDTH,
            min=0,
            max=512,
        )
        self.bg_width: IntParamHandle

        # Per-ROI clamp flags, bit i set if ROI i was clamped by the last
        # get_rois(). The inherited scalar roi_clipped is kept in step, but with
        # six boxes "something clipped" is not a useful diagnostic on its own:
        # a clipped signal box and a clipped background box mean different
        # things for the atom number.
        self.roi_clip_mask = 0

        # 1 if the two predicted signal boxes intersect. Then one port's box is
        # integrating the other port's cloud and the excitation fraction is
        # meaningless (lab book 2026-06-21: ports ~9 px apart pushed the
        # off-resonant baseline to 0.10).
        self.roi_overlap = 0

        # Count of background boxes retired this shot for sitting on the other
        # port's signal.
        self.bg_flanks_retired = 0

    @portable
    def get_rois(self) -> TArray(TInt32, 2):  # pyright: ignore[reportInvalidTypeForm]
        """Build the six grabber ROIs around the two predicted port positions.

        The grabber sees the fast-kinetics *readout frame*: the ground port
        lands at sensor y minus ``fast_kinetics_offset``, the excited port a
        further ``fast_kinetics_height`` down the frame. No gravity term is
        applied to the excited row — unlike the static configs, which displace
        their second row by ``fast_kinetics_height - excited_shift``, the
        predicted ``excited_y`` already carries all inter-shot motion (free fall
        and photon recoils alike). Adding a shift here would double-count it.
        """
        half_width = self.roi_width.get() // 2
        half_height = self.roi_height.get() // 2
        bg_width = self.bg_width.get()

        gnd_x0 = self.gnd_x - half_width
        gnd_x1 = self.gnd_x + half_width
        exc_x0 = self.excited_x - half_width
        exc_x1 = self.excited_x + half_width

        # Frame coordinates: each port's row sits in its own fast-kinetics
        # sub-frame.
        gnd_y_frame = self.gnd_y - self.fast_kinetics_offset
        exc_y_frame = (
            self.excited_y - self.fast_kinetics_offset + self.fast_kinetics_height
        )

        fill_signal_bg_roi_row(
            self.roi_buffer,
            GND_SIGNAL_ROI,
            GND_BG_LEFT_ROI,
            GND_BG_RIGHT_ROI,
            gnd_x0,
            gnd_y_frame - half_height,
            gnd_x1,
            gnd_y_frame + half_height,
            bg_width,
        )
        fill_signal_bg_roi_row(
            self.roi_buffer,
            EXC_SIGNAL_ROI,
            EXC_BG_LEFT_ROI,
            EXC_BG_RIGHT_ROI,
            exc_x0,
            exc_y_frame - half_height,
            exc_x1,
            exc_y_frame + half_height,
            bg_width,
        )

        self._flag_and_retire_overlaps(half_width, half_height, bg_width)
        self._clamp_rows_to_subframes()

        return self.roi_buffer

    @portable
    def _flag_and_retire_overlaps(self, half_width, half_height, bg_width):
        """Flag colliding signal boxes and retire contaminated background boxes.

        Worked in *sensor* coordinates, before the sub-frame shift: the two
        ports live in different sub-frames, so their frame coordinates are not
        comparable, but their physical positions on the sensor are.

        This is a nominal-geometry proxy — each port is taken at its own imaging
        time, whereas contamination is really about where the *other* cloud is
        during this port's exposure. It catches the ports-too-close regime that
        actually bites and is honest about nothing more.
        """
        gnd_x0 = self.gnd_x - half_width
        gnd_x1 = self.gnd_x + half_width
        gnd_y0 = self.gnd_y - half_height
        gnd_y1 = self.gnd_y + half_height

        exc_x0 = self.excited_x - half_width
        exc_x1 = self.excited_x + half_width
        exc_y0 = self.excited_y - half_height
        exc_y1 = self.excited_y + half_height

        # Signal on signal: not recoverable by moving boxes around, because the
        # two ports genuinely are not resolved. Flag it and let the analysis
        # mask those points.
        self.roi_overlap = 0
        if rois_intersect(
            gnd_x0, gnd_y0, gnd_x1, gnd_y1, exc_x0, exc_y0, exc_x1, exc_y1
        ):
            self.roi_overlap = 1

        # A background box sitting on the other port's cloud biases the
        # subtraction. Retiring it to zero area drops it from the pool: the
        # area-scaled correction then runs on the surviving flank alone, which
        # is a worse background estimate but an unbiased one.
        retired = 0
        if rois_intersect(
            gnd_x0 - bg_width, gnd_y0, gnd_x0, gnd_y1, exc_x0, exc_y0, exc_x1, exc_y1
        ):
            collapse_roi_in_place(self.roi_buffer, GND_BG_LEFT_ROI)
            retired += 1
        if rois_intersect(
            gnd_x1, gnd_y0, gnd_x1 + bg_width, gnd_y1, exc_x0, exc_y0, exc_x1, exc_y1
        ):
            collapse_roi_in_place(self.roi_buffer, GND_BG_RIGHT_ROI)
            retired += 1
        if rois_intersect(
            exc_x0 - bg_width, exc_y0, exc_x0, exc_y1, gnd_x0, gnd_y0, gnd_x1, gnd_y1
        ):
            collapse_roi_in_place(self.roi_buffer, EXC_BG_LEFT_ROI)
            retired += 1
        if rois_intersect(
            exc_x1, exc_y0, exc_x1 + bg_width, exc_y1, gnd_x0, gnd_y0, gnd_x1, gnd_y1
        ):
            collapse_roi_in_place(self.roi_buffer, EXC_BG_RIGHT_ROI)
            retired += 1
        self.bg_flanks_retired = retired

    @portable
    def _clamp_rows_to_subframes(self):
        """Clamp each row into its own fast-kinetics sub-frame.

        Tighter than clamping to the whole readout frame: the sub-frames are
        separate exposures stacked in one buffer, so a box allowed to spill
        across the boundary would quietly integrate rows belonging to the other
        port's image. The fast-kinetics window is only
        ``fast_kinetics_height`` tall, so clamping is routine here rather than
        exceptional — hence the per-ROI mask rather than a single flag.
        """
        height = self.fast_kinetics_height
        width = self.andor_sensor_width

        mask = 0
        for i in range(self.num_grabber_rois):
            # Even indices are the ground row (sub-frame 0), odd the excited row
            # (sub-frame 1); see the layout diagram in the module docstring.
            if i % 2 == 0:
                y_min = 0
                y_max = height
            else:
                y_min = height
                y_max = 2 * height
            if clamp_roi_in_place(self.roi_buffer, i, 0, y_min, width, y_max) != 0:
                mask |= 1 << i
        self.roi_clip_mask = mask
        self.roi_clipped = 1 if mask != 0 else 0


# %% Imaging mixins


class SingleImageDynamicROIImagingMixin(SingleImageNormalisedBase):
    """
    Single-image normalised readout with per-shot predicted ROI positions.

    Deliberately built on :class:`~.SingleImageNormalisedBase` rather than
    :class:`~.NormalisedFastKineticsBase`: this readout takes one
    fast-kinetics series, and inheriting the two-series flow would bring back
    the second acquisition, the clear-out delay and the ``images[2]``/``[3]``
    processing that spatial background exists to remove.

    Contract — the experiment base combined with this mixin must provide the
    same timebase accessors as
    :class:`~.lmt_compensated_normalised_imaging.DynamicROIImagingMixin`:
    ``dma_recording_fragment``, ``get_t_release_minus_playback_mu()`` and
    ``get_t_release_mu()``. See that class for what each one means and which
    experiment bases supply them.

    Prediction and ROI programming run once per shot in
    :meth:`before_start_hook`, off the real-time timeline with no atoms in
    flight, so the blocking RPC and the six grabber writes cannot underflow.
    They deliberately do *not* run at imaging time: reprogramming inside the
    real-time path is what drove the RTIO underflows this design replaced.
    """

    def get_andor_camera_config_hook(self) -> AndorCameraConfig:
        f = self.setattr_fragment(
            "andor_camera_config", LMTCompensatedSingleImageCameraConfig
        )
        self.andor_camera_config: LMTCompensatedSingleImageCameraConfig
        return f

    def fast_kinetics_setup_results(self):
        self.setattr_result("excitation_fraction", FloatChannel)
        self.setattr_result("atom_number", FloatChannel)
        self.setattr_result("ground_atom_number", FloatChannel)
        self.setattr_result("excited_atom_number", FloatChannel)

        self.excitation_fraction: FloatChannel
        self.atom_number: FloatChannel
        self.ground_atom_number: FloatChannel
        self.excited_atom_number: FloatChannel

    def time_dropped_before_first_pulse(self):
        # Only feeds calculate_gravitational_drop, which this readout never
        # calls: the drop between the two shots is in the predicted excited_y.
        return 0.0

    def build_fragment(self):
        super().build_fragment()

        # Re-expose the camera-config tuning params at the experiment level so
        # they can be set/scanned directly. The trap pixel is the predictor's
        # t=0 anchor and is commissioned per source.
        self.setattr_param_rebind(
            "trap_x_pixel", self.andor_camera_config, "trap_x_pixel"
        )
        self.setattr_param_rebind(
            "trap_y_pixel", self.andor_camera_config, "trap_y_pixel"
        )
        self.setattr_param_rebind("roi_width", self.andor_camera_config, "roi_width")
        self.setattr_param_rebind("roi_height", self.andor_camera_config, "roi_height")
        self.setattr_param_rebind("bg_width", self.andor_camera_config, "bg_width")

        self.setattr_param(
            "image_delay_after_sequence",
            FloatParam,
            "Delay: sequence end to first image",
            # Measured from the end of the declared sequence, so the
            # post-sequence drop is constant as the sequence grows. Scannable;
            # keeps the cloud in the short fast-kinetics z-window.
            default=constants.DEFAULT_IMAGE_DELAY_AFTER_SEQUENCE_LMT_COMPENSATED,
            unit="ms",
            min=0,
        )
        self.image_delay_after_sequence: FloatParamHandle

        # release -> first image, in seconds. Filled per shot in
        # before_start_hook and read back at imaging time, so the predicted ROIs
        # and the live camera trigger share one anchor.
        self._image_tof_s = 0.0

        # The base flow (red_mot_experiment.run_once) delays by
        # delay_after_experiment between the sequence and do_imaging_hook. We own
        # the post-sequence delay and place the image by absolute at_mu, so the
        # base delay would double-count and push now_mu past the target.
        self.override_param("delay_after_experiment", 0.0)

        self.setattr_result(
            "predicted_gnd_x", FloatChannel, display_hints={"priority": -1}
        )
        self.predicted_gnd_x: FloatChannel
        self.setattr_result(
            "predicted_gnd_y", FloatChannel, display_hints={"priority": -1}
        )
        self.predicted_gnd_y: FloatChannel
        self.setattr_result(
            "predicted_excited_x", FloatChannel, display_hints={"priority": -1}
        )
        self.predicted_excited_x: FloatChannel
        self.setattr_result(
            "predicted_excited_y", FloatChannel, display_hints={"priority": -1}
        )
        self.predicted_excited_y: FloatChannel
        self.setattr_result(
            "gnd_port_multiplicity", FloatChannel, display_hints={"priority": -1}
        )
        self.gnd_port_multiplicity: FloatChannel
        self.setattr_result(
            "excited_port_multiplicity", FloatChannel, display_hints={"priority": -1}
        )
        self.excited_port_multiplicity: FloatChannel
        self.setattr_result(
            "roi_clip_mask", FloatChannel, display_hints={"priority": -1}
        )
        self.roi_clip_mask: FloatChannel
        self.setattr_result("roi_overlap", FloatChannel, display_hints={"priority": -1})
        self.roi_overlap: FloatChannel
        self.setattr_result(
            "bg_flanks_retired", FloatChannel, display_hints={"priority": -1}
        )
        self.bg_flanks_retired: FloatChannel
        # 0 when the shot produced no usable atom number, so downstream fits can
        # drop the point. excitation_fraction keeps the static family's 0.0
        # convention in that case rather than carrying a sentinel: the archived
        # h5 copy of that channel has been seen zeroed independently of the live
        # value, so a sentinel there would not survive to the analysis.
        self.setattr_result(
            "readout_valid", FloatChannel, display_hints={"priority": -1}
        )
        self.readout_valid: FloatChannel

        # Last ROIs broadcast to the applet roi_targets datasets, so per-shot
        # re-broadcasts are skipped when the predicted ROIs are unchanged.
        # Seeded impossible so the first shot always broadcasts.
        self._last_broadcast_rois = np.full(
            (self.andor_camera_config.num_grabber_rois, 4), -1, dtype=np.int32
        )

    # ── Prediction ────────────────────────────────────────────────────────────

    @kernel
    def _predict_atom_positions(self, t_image_ground_s, t_image_excited_s):
        """Run the ROI prediction from the DMA-recorded intent buffers.

        Argument plumbing only; kept in step with the identically-named method
        on :class:`~.lmt_compensated_normalised_imaging.DynamicROIImagingMixin`,
        which cannot be shared because that class carries the two-series flow.
        """
        self.andor_camera_config.calculate_atom_positions(
            t_image_ground_s=t_image_ground_s,
            t_image_excited_s=t_image_excited_s,
            intent_start_times_mu=(
                self.dma_recording_fragment._intent_record_start_times_mu
            ),
            intent_durations_mu=(
                self.dma_recording_fragment._intent_record_durations_mu
            ),
            intent_kinds=self.dma_recording_fragment._intent_record_kinds,
            intent_state_effects=(
                self.dma_recording_fragment._intent_record_state_effects
            ),
            intent_addressed_states=(
                self.dma_recording_fragment._intent_record_addressed_states
            ),
            intent_addressed_m=self.dma_recording_fragment._intent_record_addressed_m,
            intent_delta_m=self.dma_recording_fragment._intent_record_delta_m,
            num_events=self.dma_recording_fragment._intent_record_num_events,
            t_release_minus_playback_mu=self.get_t_release_minus_playback_mu(),
        )

    @kernel
    def _sequence_end_since_release_mu(self):
        """End of the last atom-affecting event of the recorded sequence,
        relative to release, in machine units. Returns 0 for an empty stream
        (a plain drop -> anchor at release).
        """
        rec = self.dma_recording_fragment
        t_release_minus_playback_mu = self.get_t_release_minus_playback_mu()
        end_max = np.int64(0)
        for i in range(rec._intent_record_num_events):
            end = (
                rec._intent_record_start_times_mu[i]
                + rec._intent_record_durations_mu[i]
                - t_release_minus_playback_mu
            )
            if end > end_max:
                end_max = end
        return end_max

    @kernel
    def before_start_hook(self):
        # Predict and program the ROIs here: after the DMA recording populates
        # the intent buffers, before release, so the blocking RPC and the six
        # grabber writes sit in break_realtime slack with no atoms in flight.
        # The grabber holds the ROIs until re-gated, so they persist to imaging.
        self.before_start_hook_default()

        self.core.break_realtime()

        t_seq_end_s = self.core.mu_to_seconds(self._sequence_end_since_release_mu())
        self._image_tof_s = t_seq_end_s + self.image_delay_after_sequence.get()
        tof_ground = self._image_tof_s
        tof_excited = (
            tof_ground + self.andor_camera_config.fast_kinetics_time_between_shots.get()
        )
        self._predict_atom_positions(tof_ground, tof_excited)

        # The blocking RPC advanced the RTIO counter but not the cursor;
        # re-establish slack before the grabber writes (reprogram_rois does not
        # break_realtime itself).
        self.core.break_realtime()
        self.andor_camera_control.reprogram_rois()

        self.predicted_gnd_x.push(float(self.andor_camera_config.gnd_x))
        self.predicted_gnd_y.push(float(self.andor_camera_config.gnd_y))
        self.predicted_excited_x.push(float(self.andor_camera_config.excited_x))
        self.predicted_excited_y.push(float(self.andor_camera_config.excited_y))
        self.gnd_port_multiplicity.push(
            float(self.andor_camera_config.gnd_multiplicity)
        )
        self.excited_port_multiplicity.push(
            float(self.andor_camera_config.excited_multiplicity)
        )
        # get_rois() ran inside reprogram_rois, so these are current
        self.roi_clip_mask.push(float(self.andor_camera_config.roi_clip_mask))
        self.roi_overlap.push(float(self.andor_camera_config.roi_overlap))
        self.bg_flanks_retired.push(
            float(self.andor_camera_config.bg_flanks_retired)
        )

        self.core.break_realtime()

    # ── Imaging ───────────────────────────────────────────────────────────────

    @kernel
    def do_imaging_hook_andor(self):
        # ROIs were predicted and programmed in before_start_hook, which also
        # stamped _image_tof_s (= sequence end since release + the chosen
        # post-sequence delay). Place the first fast-kinetics image there; the
        # second follows by delay_between_imaging_pulses inside do_image.
        t_image_mu = self.get_t_release_mu() + self.core.seconds_to_mu(
            self._image_tof_s
        )
        if t_image_mu < now_mu():
            # The sequence has already run past the requested imaging time, so
            # at_mu() would rewind the cursor and underflow at the pulse. Fail
            # loudly instead: the usual cause is a sequence that outran the
            # intent stream the prediction was anchored on, which would also
            # have put the ROIs in the wrong place.
            raise RuntimeError(
                "Imaging time precedes the end of the post-release sequence. "
                "Increase image_delay_after_sequence."
            )
        at_mu(t_image_mu)
        # ARTIQ kernels do not support super(); call the base flow by name.
        self.do_image()

    @kernel
    def process_grabber_data_hook(self, sums, means):
        rois = self.andor_camera_config.get_rois()
        areas = [np.int32(0)] * NUM_SINGLE_IMAGE_DYNAMIC_ROIS
        for i in range(NUM_SINGLE_IMAGE_DYNAMIC_ROIS):
            areas[i] = self.andor_camera_config.calculate_area_from_roi(rois[i])

        ground_atom_number = background_corrected_counts(
            sums, areas, GND_SIGNAL_ROI, GND_BG_LEFT_ROI, GND_BG_RIGHT_ROI
        )
        excited_atom_number = background_corrected_counts(
            sums, areas, EXC_SIGNAL_ROI, EXC_BG_LEFT_ROI, EXC_BG_RIGHT_ROI
        )
        atom_number = ground_atom_number + excited_atom_number

        if atom_number == 0.0:
            self.excitation_fraction.push(0.0)
            self.readout_valid.push(0.0)
        else:
            self.excitation_fraction.push(excited_atom_number / atom_number)
            self.readout_valid.push(1.0)

        self.atom_number.push(atom_number)
        self.ground_atom_number.push(ground_atom_number)
        self.excited_atom_number.push(excited_atom_number)

    # ── Applet overlays ───────────────────────────────────────────────────────

    @host_only
    def get_monitor_rois(self):
        return np.array(
            self.andor_camera_config.get_rois()[
                [GND_SIGNAL_ROI, GND_BG_LEFT_ROI, GND_BG_RIGHT_ROI]
            ]
        ).tolist()

    @kernel
    def _rois_changed_since_last_broadcast(self, rois):
        """True if ``rois`` differs from the last broadcast, updating the cache.

        Gates the per-shot dataset re-broadcast so unchanged ROIs cost nothing.
        """
        changed = False
        for i in range(self.andor_camera_config.num_grabber_rois):
            for j in range(4):
                if rois[i][j] != self._last_broadcast_rois[i][j]:
                    changed = True
                    self._last_broadcast_rois[i][j] = rois[i][j]
        return changed

    @rpc(flags={"async"})
    def _broadcast_dynamic_roi_targets(self, rois) -> None:
        """Re-broadcast the roi_targets datasets so the applet overlay tracks the
        predicted ROIs.

        The background boxes are drawn alongside the signal boxes: when a
        background box is what clipped or got retired, an overlay showing only
        the signal box would look perfectly healthy while the subtraction it
        feeds was not.

        Driven from the kernel-side :meth:`after_save_andor_data_hook` with the
        live ``rois``, because the predicted positions are only current
        kernel-side — the host copy is a shot behind.
        """
        ground_indices = (GND_SIGNAL_ROI, GND_BG_LEFT_ROI, GND_BG_RIGHT_ROI)
        excited_indices = (EXC_SIGNAL_ROI, EXC_BG_LEFT_ROI, EXC_BG_RIGHT_ROI)
        fk_height = self.andor_camera_config.fast_kinetics_height

        ground, excited = self._split_bg_corrected_roi_targets(
            rois, fk_height, ground_indices, excited_indices
        )
        self.set_dataset(ANDOR_FK_G_BG_CORR_ROI_TARGETS_DATASET, ground, broadcast=True)
        self.set_dataset(
            ANDOR_FK_E_BG_CORR_ROI_TARGETS_DATASET, excited, broadcast=True
        )
        self.set_dataset(
            ANDOR_MONITOR_ROI_TARGETS_DATASET,
            self._composite_monitor_roi_targets(
                rois, fk_height, ground_indices, excited_indices
            ),
            broadcast=True,
        )

    @kernel
    def after_save_andor_data_hook(self):
        # Keep the applet ROI overlay in step with the grabber, but only when the
        # predicted ROIs actually moved.
        rois = self.andor_camera_config.get_rois()
        if self._rois_changed_since_last_broadcast(rois):
            self._broadcast_dynamic_roi_targets(rois)


class SingleImageLMTClockPulseMixin(SingleImageNormalisedBase, ClockSpectroscopyBase):
    """
    Momentum-resolving clock selection pulse for the single-image readout.

    The single-image family's own
    :class:`~.single_image_normalised_fast_kinetics_base.RepumpingWithClockMixin`
    fires a plain pi pulse and does not compensate the free-fall Doppler shift,
    which is fine for a trapped cloud but not for the LMT readout, where the
    atoms have been falling for the whole sequence. This reproduces the
    two-series
    :class:`~.normalised_fast_kinetics_base.NormalisedFastKineticsClockPulseMixin`
    pulse instead: full delivery power, OPLL on the free-fall resonance, and a
    Fourier-broad DOWN pi.

    Kernel hooks used (multiple mixins cannot use the same hooks):

    * :meth:`~do_first_pulse`
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

        # A truncated sequence can leave the delivery servo at whatever setpoint
        # its last executed event set (e.g. the low shelving setpoint after a
        # slice-only truncation), so drive it to full power here. This makes the
        # readout a full-power, fast (Fourier-broad) DOWN pi identical in speed
        # to the launch/mirror pulses - the M-state-resolving selection pulse.
        self.set_clock_delivery_aom(
            freq=self.calculate_clock_delivery_freq(now_mu(), 0.0),
            setpoint_v=CLOCK_DELIVERY_SETPOINT_V,
        )
        delay(constants.CLOCK_DELIVERY_PREEMPT_TIME)

        # Put the OPLL on the free-fall Doppler resonance the falling atoms
        # actually see. Called before the switch-DDS write so the OPLL write
        # gets a ladder-like settling margin before the switch opens.
        self._set_readout_opll_for_fall()

        self.clock_down_dds.set(
            frequency=self.clock_switch_frequency_handle.get()
            + self.imaging_clock_pulse_detuning.get()
            # Matches both existing clock readout paths, which apply the DOWN
            # beam shift here rather than in the launch sequence.
            + constants.LMT_DOWN_BEAM_SHIFT,
            amplitude=self.clock_switch_amplitude_handle.get(),
        )

        delay(1e-6)

        self.clock_down_dds.sw.on()
        delay(constants.DOWN_CLOCK_BEAM_PI_TIME)
        self.clock_down_dds.sw.off()

    @kernel
    def _set_readout_opll_for_fall(self):
        """Set readout OPLL to the free-fall Doppler resonance at pulse time."""
        t_release_mu = (
            self.get_t_release_mu()
        )  # pyright: ignore[reportAttributeAccessIssue]
        t_fall = self.core.mu_to_seconds(now_mu() - t_release_mu)
        self.set_clock_opll(  # pyright: ignore[reportAttributeAccessIssue]
            READOUT_START_OPLL_OFFSET
            + READOUT_BEAM_SIGN * t_fall * constants.GRAVITY_DOPPLER_PER_SEC_CLOCK
        )


# %% Aggregators


class SingleImageLMTCorrectedMixin(
    SingleImageDynamicROIImagingMixin,
    RepumpingWith679Mixin,
):
    """
    Predicted ROIs with spatial background from
    :class:`~.SingleImageDynamicROIImagingMixin` (which wins
    ``do_imaging_hook_andor`` / ``get_andor_camera_config_hook`` in the MRO) plus
    the 679/707 repump of
    :class:`~.single_image_normalised_fast_kinetics_base.RepumpingWith679Mixin`
    (which wins ``do_first_pulse``).

    This is the single-image counterpart of
    :class:`~.lmt_compensated_normalised_imaging.NormalisedFastKineticsLMTCorrectedMixin`.
    For momentum-resolved readout use :class:`~.SingleImageLMTCorrectedClockMixin`.

    Do not also mix in a static-config imaging mixin: they contend for
    ``get_andor_camera_config_hook`` and the ROI positions would come from
    whichever won. See :class:`~.SingleImageDynamicROIImagingMixin` for the
    timebase-accessor contract the experiment base must satisfy.
    """


class SingleImageLMTCorrectedClockMixin(
    SingleImageDynamicROIImagingMixin,
    SingleImageLMTClockPulseMixin,
):
    """
    As :class:`~.SingleImageLMTCorrectedMixin`, but ``do_first_pulse`` is the
    full-power broad clock selection pulse of
    :class:`~.SingleImageLMTClockPulseMixin` instead of the 679/707 repump.

    Scanning ``imaging_clock_pulse_detuning`` then resolves adjacent momentum
    (M-)states. Repumped vs clock readout is a compile-time choice: name
    whichever aggregator you want in the experiment Frag's bases.
    """
