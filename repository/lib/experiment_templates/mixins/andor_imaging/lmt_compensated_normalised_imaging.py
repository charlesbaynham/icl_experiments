"""
Dynamic-ROI normalised fast-kinetics imaging.

The camera ROIs are repositioned every shot from the recorded pulse-intent
trajectory: the kernel RPCs the intent stream to a host predictor that returns
the ground/excited port pixels at the two fast-kinetics shot times, and the
grabber ROIs are reprogrammed to track the falling clouds.
"""

import logging

import numpy as np
from artiq.language import TArray
from artiq.language import TBool
from artiq.language import TFloat
from artiq.language import TInt32
from artiq.language import TInt64
from artiq.language import TList
from artiq.language import at_mu
from artiq.language import kernel
from artiq.language import portable
from artiq.language import rpc
from ndscan.experiment import FloatChannel
from ndscan.experiment.parameters import FloatParam
from ndscan.experiment.parameters import FloatParamHandle
from ndscan.experiment.parameters import IntParam
from ndscan.experiment.parameters import IntParamHandle
from numpy import int64

from repository.lib import constants
from repository.lib.experiment_templates.mixins.andor_imaging.imaging_base import (
    ANDOR_FK_E_BG_CORR_ROI_TARGETS_DATASET,
)
from repository.lib.experiment_templates.mixins.andor_imaging.imaging_base import (
    ANDOR_FK_G_BG_CORR_ROI_TARGETS_DATASET,
)
from repository.lib.experiment_templates.mixins.andor_imaging.normalised_fast_kinetics_base import (
    NormalisedFastKineticsBase,
)
from repository.lib.experiment_templates.mixins.andor_imaging.normalised_fast_kinetics_base import (
    NormalisedFastKineticsRepumpedMixin,
)
from repository.lib.fragments.cameras.andor_camera import AndorCameraConfig
from repository.lib.fragments.cameras.andor_camera import FastKineticsCameraConfig
from repository.lib.physics import lmt_resonance
from repository.lib.physics import trajectory
from repository.lib.physics.ballistic import BallisticConfig
from repository.lib.physics.ballistic import CameraGeometry

logger = logging.getLogger(__name__)


# %% Utility functions


@portable
def _fill_clamped_roi(
    roi_buffer,
    index,
    centre_x,
    centre_y_frame,
    half_width,
    half_height,
    frame_width,
    frame_height,
) -> TInt32:  # pyright: ignore[reportInvalidTypeForm]
    """Write one ROI centred on a predicted position into ``roi_buffer``.

    Clamped to the readout frame, then ordering is enforced (``x1 >= x0``,
    ``y1 >= y0``) so a fully off-frame prediction is degenerate-but-valid, never
    negative-area. Returns 1 if any coordinate had to be clamped, else 0.
    """
    x0 = centre_x - half_width
    y0 = centre_y_frame - half_height
    x1 = centre_x + half_width
    y1 = centre_y_frame + half_height

    cx0 = min(max(x0, 0), frame_width)
    cy0 = min(max(y0, 0), frame_height)
    cx1 = min(max(x1, 0), frame_width)
    cy1 = min(max(y1, 0), frame_height)

    clipped = 0
    if cx0 != x0 or cy0 != y0 or cx1 != x1 or cy1 != y1:
        clipped = 1

    cx1 = max(cx1, cx0)
    cy1 = max(cy1, cy0)

    roi_buffer[index][0] = cx0
    roi_buffer[index][1] = cy0
    roi_buffer[index][2] = cx1
    roi_buffer[index][3] = cy1
    return clipped


# %% Camera config


class LMTCompensatedCameraConfig(FastKineticsCameraConfig):
    """
    Andor config that repositions ROIs from the predicted cloud trajectory.

    :meth:`calculate_atom_positions` RPCs the host predictor
    (:func:`repository.lib.physics.trajectory.predict_port_pixels`) to fill
    ``gnd_x/y``, ``excited_x/y`` and the port multiplicities; :meth:`get_rois`
    then builds ROIs centred on those pixels. The camera geometry is fixed in
    :mod:`repository.lib.constants`; only the trap pixel and ROI size are
    tunable params (per-source commissioning).
    """

    num_andor_images = 4
    num_images_per_series = 2
    num_grabber_rois = 2
    num_grabber_readouts = 2
    fast_kinetics_num_shots = 2

    fast_kinetics_height = constants.ANDOR_FAST_KINETICS_HEIGHT
    fast_kinetics_offset = constants.ANDOR_FAST_KINETICS_OFFSET

    def build_fragment(self):
        super().build_fragment()

        self.setattr_device("core")

        self.setattr_param(
            "roi_width",
            IntParam,
            "Width of the ROI (pixels)",
            default=constants.DEFAULT_ROI_WIDTH,
            min=1,
            max=1024,
        )
        self.roi_width: IntParamHandle

        self.setattr_param(
            "roi_height",
            IntParam,
            "Height of the ROI (pixels)",
            default=constants.DEFAULT_ROI_HEIGHT,
            min=1,
            max=1024,
        )
        self.roi_height: IntParamHandle

        # Trap position on the sensor (pixel coordinates at t=0)
        self.setattr_param(
            "trap_x_pixel",
            IntParam,
            "Pixel x coordinate of the trap centre",
            default=constants.ATOM_POSITION_T0[0],
            min=0,
            max=constants.ANDOR_CAMERA_FACTS["sensor_width"],
        )
        self.trap_x_pixel: IntParamHandle

        self.setattr_param(
            "trap_y_pixel",
            IntParam,
            "Pixel y coordinate of the trap centre",
            default=constants.ATOM_POSITION_T0[1],
            min=0,
            max=constants.ANDOR_CAMERA_FACTS["sensor_height"],
        )
        self.trap_y_pixel: IntParamHandle

        # Kernel variables — pixel positions (sensor coordinates) and port
        # multiplicities filled by calculate_atom_positions
        self.gnd_x = 0
        self.gnd_y = 0
        self.excited_x = 0
        self.excited_y = 0
        self.gnd_multiplicity = 0
        self.excited_multiplicity = 0

        # 1 if the last get_rois() call had to clamp an ROI to the readout
        # frame, 0 otherwise. Read by the imaging mixin for diagnostics.
        self.roi_clipped = 0

        self.roi_buffer = np.zeros((self.num_grabber_rois, 4), dtype=np.int32)

        # Cache sensor dimensions as kernel invariants
        self.andor_sensor_width = constants.ANDOR_CAMERA_FACTS["sensor_width"]
        self.andor_sensor_height = constants.ANDOR_CAMERA_FACTS["sensor_height"]
        self.kernel_invariants = getattr(self, "kernel_invariants", set())
        self.kernel_invariants.add("andor_sensor_width")
        self.kernel_invariants.add("andor_sensor_height")

    # ── ROI calculation ───────────────────────────────────────────────────────

    @portable
    def get_rois(self) -> TArray(TInt32, 2):  # pyright: ignore[reportInvalidTypeForm]
        """Build the two grabber ROIs centred on the predicted port positions.

        The grabber sees the fast-kinetics *readout frame*: the first shot
        (ground port) lands at sensor y minus ``fast_kinetics_offset``, the
        second (excited port) a further ``fast_kinetics_height`` down the frame.
        Physical inter-shot motion is already in the predicted ``excited_y``, so
        no extra shift is applied. Clamping is recorded in ``roi_clipped``.
        """
        half_width = self.roi_width.get() // 2
        half_height = self.roi_height.get() // 2
        frame_height = 2 * self.fast_kinetics_height

        gnd_y_frame = self.gnd_y - self.fast_kinetics_offset
        excited_y_frame = (
            self.excited_y - self.fast_kinetics_offset + self.fast_kinetics_height
        )

        clipped = 0
        if (
            _fill_clamped_roi(
                self.roi_buffer,
                0,
                self.gnd_x,
                gnd_y_frame,
                half_width,
                half_height,
                self.andor_sensor_width,
                frame_height,
            )
            != 0
        ):
            clipped = 1
        if (
            _fill_clamped_roi(
                self.roi_buffer,
                1,
                self.excited_x,
                excited_y_frame,
                half_width,
                half_height,
                self.andor_sensor_width,
                frame_height,
            )
            != 0
        ):
            clipped = 1
        self.roi_clipped = clipped

        return self.roi_buffer

    def host_setup(self):
        # Initialise gnd/excited to the trap centre so that get_rois() -
        # called on the host by the base class's host_setup validation -
        # returns sensible ROIs even before calculate_atom_positions runs.
        self.gnd_x = int(self.trap_x_pixel.get())
        self.gnd_y = int(self.trap_y_pixel.get())
        self.excited_x = self.gnd_x
        self.excited_y = self.gnd_y
        super().host_setup()

    # ── Intent-driven predictor ───────────────────────────────────────────────

    @kernel
    def calculate_atom_positions(
        self,
        t_image_ground_s: TFloat,
        t_image_excited_s: TFloat,
        intent_start_times_mu: TList(TInt64),  # pyright: ignore[reportInvalidTypeForm]
        intent_durations_mu: TList(TInt64),  # pyright: ignore[reportInvalidTypeForm]
        intent_kinds: TList(TInt32),  # pyright: ignore[reportInvalidTypeForm]
        intent_state_effects: TList(TInt32),  # pyright: ignore[reportInvalidTypeForm]
        intent_addressed_states: TList(  # pyright: ignore[reportInvalidTypeForm]
            TInt32
        ),
        intent_addressed_m: TList(TInt32),  # pyright: ignore[reportInvalidTypeForm]
        intent_delta_m: TList(TInt32),  # pyright: ignore[reportInvalidTypeForm]
        num_events: TInt32,
        t_release_minus_playback_mu: TInt64,
    ) -> None:
        """Predict cloud pixels at the two imaging times of flight and store
        them in ``gnd_x/y``, ``excited_x/y`` and the multiplicities.

        Deterministic in the recorded intent stream and build-time constants,
        so it can run in ``before_start_hook`` (before release): image times
        enter only as time-of-flight, recorded events only relative to release,
        and the absolute playback cursor cancels.

        ``t_release_minus_playback_mu`` is ``t_release_mu - t_playback_start_mu``
        (mu); recorded events fire at ``t_playback_start + t_recorded``, so their
        time since release is ``t_recorded - t_release_minus_playback``.
        """
        # Slice to num_events BEFORE the RPC: the buffers are BUFFER_DEPTH (300)
        # long and marshalling all of them kernel->host costs timeline slack.
        packed = self._calculate_positions_host(
            t_image_ground_s,
            t_image_excited_s,
            intent_start_times_mu[:num_events],
            intent_durations_mu[:num_events],
            intent_kinds[:num_events],
            intent_state_effects[:num_events],
            intent_addressed_states[:num_events],
            intent_addressed_m[:num_events],
            intent_delta_m[:num_events],
            num_events,
            t_release_minus_playback_mu,
        )
        self.gnd_x = packed[0]
        self.gnd_y = packed[1]
        self.excited_x = packed[2]
        self.excited_y = packed[3]
        self.gnd_multiplicity = packed[4]
        self.excited_multiplicity = packed[5]

    @rpc
    def _calculate_positions_host(
        self,
        t_image_ground_s: TFloat,
        t_image_excited_s: TFloat,
        intent_start_times_mu: TList(TInt64),  # pyright: ignore[reportInvalidTypeForm]
        intent_durations_mu: TList(TInt64),  # pyright: ignore[reportInvalidTypeForm]
        intent_kinds: TList(TInt32),  # pyright: ignore[reportInvalidTypeForm]
        intent_state_effects: TList(TInt32),  # pyright: ignore[reportInvalidTypeForm]
        intent_addressed_states: TList(  # pyright: ignore[reportInvalidTypeForm]
            TInt32
        ),
        intent_addressed_m: TList(TInt32),  # pyright: ignore[reportInvalidTypeForm]
        intent_delta_m: TList(TInt32),  # pyright: ignore[reportInvalidTypeForm]
        num_events: TInt32,
        t_release_minus_playback_mu: TInt64,
    ) -> TArray(TInt32, 1):  # pyright: ignore[reportInvalidTypeForm]
        """Host-side predictor: returns ``[gnd_x, gnd_y, exc_x, exc_y,
        gnd_multiplicity, exc_multiplicity]`` as int32."""
        camera = CameraGeometry(
            optical_axis=constants.ANDOR_OPTICAL_AXIS,
            sensor_x_axis=constants.ANDOR_SENSOR_X_AXIS,
            sensor_y_axis=constants.ANDOR_SENSOR_Y_AXIS,
            centre_pixel=(
                float(self.trap_x_pixel.get()),
                float(self.trap_y_pixel.get()),
            ),
            pixel_size_m=constants.ANDOR_CAMERA_FACTS["pixel_size"],
            magnification=constants.ANDOR_CAMERA_FACTS["magnification"],
        )
        cfg = BallisticConfig(
            mass_kg=constants.SR_ATOM_MASS_KG,
            gravity_vec_m_per_s2=constants.GRAVITY_VEC_M_PER_S2,
            clock_beam_direction=constants.CLOCK_UP_BEAM_DIRECTION,
            clock_wavelength_m=constants.CLOCK_WAVELENGTH_M,
            camera=camera,
        )

        # Rebase recording-relative timestamps to seconds since release. Only
        # the difference (t_release - t_playback) is needed, so feed it as the
        # release time with a zero playback origin.
        t_start_s = trajectory.rebase_record_times_mu(
            intent_start_times_mu[:num_events],
            0,
            t_release_minus_playback_mu,
            self.core.ref_period,
        )
        duration_s = (
            np.asarray(intent_durations_mu[:num_events], dtype=np.int64)
            * self.core.ref_period
        )

        # An empty stream (num_events == 0) is handled by predict_port_pixels
        # as pure free fall.
        events = lmt_resonance.intent_events_from_arrays(
            t_start_s=t_start_s,
            duration_s=duration_s,
            kinds=intent_kinds[:num_events],
            state_effects=intent_state_effects[:num_events],
            addressed_states=intent_addressed_states[:num_events],
            addressed_m=intent_addressed_m[:num_events],
            delta_m=intent_delta_m[:num_events],
        )

        # The image times are chosen times of flight (seconds since release).
        out = trajectory.predict_port_pixels(
            events,
            t_image_ground_s=t_image_ground_s,
            t_image_excited_s=t_image_excited_s,
            cfg=cfg,
        )
        gnd = out["ground"]
        exc = out["excited"]

        # No logging in this per-shot path: positions and multiplicities are
        # published on the diagnostics result channels instead. Multiplicity 0
        # (empty port) or >1 (open interferometer) still yields sensible ROIs.
        return np.array(
            [
                int(round(gnd.x_pixel)),
                int(round(gnd.y_pixel)),
                int(round(exc.x_pixel)),
                int(round(exc.y_pixel)),
                gnd.multiplicity,
                exc.multiplicity,
            ],
            dtype=np.int32,
        )


# %% Imaging mixins


class DynamicROIImagingMixin(NormalisedFastKineticsBase):
    """
    :class:`~.NormalisedFastKineticsBase` using :class:`~LMTCompensatedCameraConfig`
    to reposition the ROIs from the predicted cloud trajectory.

    Contract — the experiment base combined with this mixin must provide:

    * ``dma_recording_fragment``: a
      :class:`~repository.lib.fragments.pulse_recorder_and_tracker.PulseDMARecording`
      whose intent buffers describe the recorded sequence (provided by
      :class:`~repository.lib.experiment_templates.dipole_trap_experiment.DipoleTrapWithExperimentBase`).
    * ``get_t_release_minus_playback_mu() -> TInt64`` (``@portable``): the
      release time relative to the DMA playback origin
      (``t_release_mu - t_playback_start_mu``), in machine units. This is all
      the prediction needs (the absolute playback cursor cancels), and it is
      knowable in ``before_start_hook`` before either live timestamp is
      stamped. ``DipoleTrapWithExperimentBase`` returns ``+t_dipole_beams_off``
      (the drop is stamped inside the recording); ``DMAActionsAfterDropMixin``
      returns ``-seconds_to_mu(expansion_time)`` (the red-MOT release precedes
      playback by ``expansion_time``).
    * ``get_t_release_mu() -> TInt64`` (``@portable``): the *live-timeline*
      machine-unit timestamp of the atom release. Used at imaging time to pin
      the first fast-kinetics image at ``t_release + (sequence end since
      release) + image_delay_after_sequence``.

    Prediction + ROI programming runs once per shot in :meth:`before_start_hook`
    (off the RT timeline, no atoms in flight, so the blocking RPC and grabber
    writes cannot underflow), overwriting the trap-centre ROIs ``device_setup``
    programs at shot start. Diagnostics channels (predicted positions, port
    multiplicities, ROI clamp flag) are pushed once per shot there.

    Overrides :meth:`get_andor_camera_config_hook`, :meth:`before_start_hook`
    and :meth:`do_imaging_hook_andor`.
    """

    def get_andor_camera_config_hook(self) -> AndorCameraConfig:
        f = self.setattr_fragment("andor_camera_config", LMTCompensatedCameraConfig)
        self.andor_camera_config: LMTCompensatedCameraConfig
        return f

    def build_fragment(self):
        super().build_fragment()

        # Re-expose the camera-config tuning params at the experiment level so
        # they can be set/scanned directly (otherwise only reachable at a nested
        # override path). The trap pixel is source-specific (red MOT vs dipole
        # trap sit at different sensor positions) and commissioned per source.
        self.setattr_param_rebind(
            "trap_x_pixel", self.andor_camera_config, "trap_x_pixel"
        )
        self.setattr_param_rebind(
            "trap_y_pixel", self.andor_camera_config, "trap_y_pixel"
        )
        self.setattr_param_rebind("roi_width", self.andor_camera_config, "roi_width")
        self.setattr_param_rebind("roi_height", self.andor_camera_config, "roi_height")

        self.setattr_param(
            "image_delay_after_sequence",
            FloatParam,
            "Delay: sequence end to first image",
            # Measured from the end of the declared sequence, so the post-sequence
            # drop is constant as the sequence grows.
            # Scannable; keeps the cloud in the short fast-kinetics z-window.
            default=500e-6,
            unit="ms",
            min=0,
        )
        self.image_delay_after_sequence: FloatParamHandle

        # release -> first image, in seconds. Filled per shot in
        # before_start_hook (= sequence end since release + the delay above) and
        # read back at imaging time, so the predicted ROIs and the live camera
        # trigger share one anchor.
        self._image_tof_s = 0.0

        # The base flow (red_mot_experiment.run_once) does
        # delay(delay_after_experiment) between the sequence and do_imaging_hook.
        # We own the post-sequence delay (image_delay_after_sequence) and place
        # the image by absolute at_mu, so the base delay would only double-count
        # and push now_mu past our target. Zero it; this mixin's delay is the
        # single post-sequence delay (cf. midway_imaging).
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
        self.setattr_result("roi_clipped", FloatChannel, display_hints={"priority": -1})
        self.roi_clipped: FloatChannel
        self.setattr_result(
            "gnd_port_multiplicity", FloatChannel, display_hints={"priority": -1}
        )
        self.gnd_port_multiplicity: FloatChannel
        self.setattr_result(
            "excited_port_multiplicity", FloatChannel, display_hints={"priority": -1}
        )
        self.excited_port_multiplicity: FloatChannel

        # Last ROIs broadcast to the applet roi_targets datasets, so per-shot
        # re-broadcasts are skipped when the predicted ROIs are unchanged.
        # Seeded impossible so the first shot always broadcasts.
        self._last_broadcast_rois = np.full(
            (self.andor_camera_config.num_grabber_rois, 4), -1, dtype=np.int32
        )

    @kernel
    def _predict_atom_positions(
        self, t_image_ground_s: TFloat, t_image_excited_s: TFloat
    ):
        """Run the ROI prediction from the DMA-recorded intent buffers and the
        recording-relative release offset, so it can run in
        :meth:`before_start_hook` before the atoms are released.
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
    def _sequence_end_since_release_mu(
        self,
    ) -> TInt64:  # pyright: ignore[reportInvalidTypeForm]
        """End of the last atom-affecting event of the recorded sequence,
        relative to release, in machine units.

        Reads the DMA-recorded intent stream (populated before release), whose
        timings relative to release equal the live (DMA-replayed) timeline's.
        Returns 0 for an empty stream (a plain drop -> anchor at release).
        """
        rec = self.dma_recording_fragment
        t_release_minus_playback_mu = self.get_t_release_minus_playback_mu()
        end_max = int64(0)
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
        # the intent buffers, before release, so the blocking RPC + grabber
        # writes sit in break_realtime slack with no atoms in flight. The
        # grabber holds the ROIs until re-gated, so they persist to imaging.
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
        # get_rois() ran inside reprogram_rois, so roi_clipped is current
        self.roi_clipped.push(float(self.andor_camera_config.roi_clipped))

        self.core.break_realtime()

    @kernel
    def _rois_changed_since_last_broadcast(
        self, rois: TArray(TInt32, 2)  # pyright: ignore[reportInvalidTypeForm]
    ) -> TBool:  # pyright: ignore[reportInvalidTypeForm]
        """True if ``rois`` differs from the last broadcast, updating the cache.

        Element-wise over the (num_grabber_rois x 4) buffer; cheap, and gates the
        per-shot dataset re-broadcast so unchanged ROIs cost nothing.
        """
        changed = False
        for i in range(self.andor_camera_config.num_grabber_rois):
            for j in range(4):
                if rois[i][j] != self._last_broadcast_rois[i][j]:
                    changed = True
                    self._last_broadcast_rois[i][j] = rois[i][j]
        return changed

    @rpc(flags={"async"})
    def _broadcast_dynamic_roi_targets(
        self, rois: TArray(TInt32, 2)  # pyright: ignore[reportInvalidTypeForm]
    ) -> None:
        """Re-broadcast the bg-corrected roi_targets datasets so the live applet
        overlay tracks the per-shot predicted ROIs (ROI 0 = ground, ROI 1 =
        excited)."""
        ground, excited = self._split_bg_corrected_roi_targets(
            rois, self.andor_camera_config.fast_kinetics_height
        )
        self.set_dataset(ANDOR_FK_G_BG_CORR_ROI_TARGETS_DATASET, ground, broadcast=True)
        self.set_dataset(
            ANDOR_FK_E_BG_CORR_ROI_TARGETS_DATASET, excited, broadcast=True
        )

    @kernel
    def after_save_andor_data_hook(self):
        # Keep the applet ROI overlay in step with the grabber: re-broadcast the
        # roi_targets datasets, but only when the predicted ROIs actually moved.
        rois = self.andor_camera_config.get_rois()
        if self._rois_changed_since_last_broadcast(rois):
            self._broadcast_dynamic_roi_targets(rois)

    @kernel
    def do_imaging_hook_andor(self):
        # ROIs were already predicted and programmed in before_start_hook, which
        # also stamped _image_tof_s (= sequence end since release + the chosen
        # post-sequence delay). Place the first fast-kinetics image there; the
        # second follows by fast_kinetics_time_between_shots (handled by the base
        # imaging series).
        t_image_mu = self.get_t_release_mu() + self.core.seconds_to_mu(
            self._image_tof_s
        )
        at_mu(t_image_mu)
        # ARTIQ kernels do not support super(); call the base implementation
        # by name instead
        self.do_imaging_hook_andor_default()


class NormalisedFastKineticsLMTCorrectedMixin(
    DynamicROIImagingMixin,
    NormalisedFastKineticsRepumpedMixin,
    # NormalisedFastKineticsClockPulseMixin  FIXME Put back the clock pulse imaging
):
    """
    Dynamic ROIs from :class:`~.DynamicROIImagingMixin` (which wins
    ``do_imaging_hook_andor`` / ``get_andor_camera_config_hook`` in the MRO)
    plus the clock pi pulse of :class:`~.NormalisedFastKineticsClockPulseMixin`
    (which still wins ``do_first_pulse``).

    ``DynamicROIImagingMixin`` is listed first so its precedence over the
    static-config base hooks is explicit. See
    :class:`~.DynamicROIImagingMixin` for the timebase-accessor contract.
    """
