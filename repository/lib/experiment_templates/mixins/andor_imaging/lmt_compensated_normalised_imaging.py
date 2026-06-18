"""
Dynamic-ROI normalised fast-kinetics imaging.

The camera ROIs are repositioned every shot along the trajectory predicted
from the recorded pulse *intent* stream (see
:mod:`repository.lib.pulse_intent` and
:mod:`repository.lib.physics.trajectory`): just before imaging, the kernel
RPCs the recorded intent events to the host predictor, which walks the
declared population branches and returns the expected sensor positions of
the ground and excited detection ports at the two fast-kinetics shot times.
The grabber ROIs are then reprogrammed mid-shot to track the falling clouds.
"""

import logging

import numpy as np
from artiq.language import TArray
from artiq.language import TInt32
from artiq.language import TInt64
from artiq.language import TList
from artiq.language import at_mu
from artiq.language import kernel
from artiq.language import now_mu
from artiq.language import portable
from artiq.language import rpc
from ndscan.experiment import FloatChannel
from ndscan.experiment.parameters import FloatParam
from ndscan.experiment.parameters import FloatParamHandle
from ndscan.experiment.parameters import IntParam
from ndscan.experiment.parameters import IntParamHandle

from repository.lib import constants
from repository.lib import pulse_intent
from repository.lib.experiment_templates.mixins.andor_imaging.normalised_fast_kinetics_base import (
    NormalisedFastKineticsBase,
)
from repository.lib.experiment_templates.mixins.andor_imaging.normalised_fast_kinetics_base import (
    NormalisedFastKineticsClockPulseMixin,
)
from repository.lib.fragments.cameras.andor_camera import AndorCameraConfig
from repository.lib.fragments.cameras.andor_camera import FastKineticsCameraConfig
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
    """Write one ROI centred on a predicted position into a preallocated buffer.

    The ROI is clamped to the readout frame ``[0, frame_width] x
    [0, frame_height]``. After clamping, ordering is enforced (``x1 >= x0``,
    ``y1 >= y0``) so a fully off-frame prediction yields a degenerate-but-valid
    ROI, never one with negative area.

    Returns:
        1 if any coordinate had to be clamped, else 0.
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
    Andor camera configuration that dynamically repositions ROIs based on
    the trajectory of the atom clouds predicted from the recorded pulse
    intent stream.

    Call :meth:`calculate_atom_positions` once between DMA playback and the
    first fluorescence pulse. It RPC-calls the host-side intent-driven
    predictor (:func:`repository.lib.physics.trajectory.predict_port_pixels`)
    which fills ``gnd_x/y``, ``excited_x/y`` and the port multiplicities;
    :meth:`get_rois` then builds ROIs centred on those pixel positions.

    Camera geometry is fully configurable via ndscan parameters so that
    small unknown tilts can be corrected without code changes.
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
            default=constants.ANDOR_TRAP_CENTRE_X_PIXEL,
            min=0,
            max=constants.ANDOR_CAMERA_FACTS["sensor_width"],
        )
        self.trap_x_pixel: IntParamHandle

        self.setattr_param(
            "trap_y_pixel",
            IntParam,
            "Pixel y coordinate of the trap centre",
            default=constants.ANDOR_TRAP_CENTRE_Y_PIXEL,
            min=0,
            max=constants.ANDOR_CAMERA_FACTS["sensor_height"],
        )
        self.trap_y_pixel: IntParamHandle

        # Camera orientation — three lab-frame unit vectors
        # Defaults from constants; operators can fine-tune tilts from the ndscan UI.
        ax, ay, az = constants.ANDOR_OPTICAL_AXIS_DEFAULT
        self.setattr_param(
            "optical_axis_x",
            FloatParam,
            "Optical axis x (lab frame)",
            default=float(ax),
        )
        self.optical_axis_x: FloatParamHandle
        self.setattr_param(
            "optical_axis_y",
            FloatParam,
            "Optical axis y (lab frame)",
            default=float(ay),
        )
        self.optical_axis_y: FloatParamHandle
        self.setattr_param(
            "optical_axis_z",
            FloatParam,
            "Optical axis z (lab frame)",
            default=float(az),
        )
        self.optical_axis_z: FloatParamHandle

        sx, sy, sz = constants.ANDOR_SENSOR_X_AXIS_DEFAULT
        self.setattr_param(
            "sensor_x_x", FloatParam, "Sensor +x axis x (lab frame)", default=float(sx)
        )
        self.sensor_x_x: FloatParamHandle
        self.setattr_param(
            "sensor_x_y", FloatParam, "Sensor +x axis y (lab frame)", default=float(sy)
        )
        self.sensor_x_y: FloatParamHandle
        self.setattr_param(
            "sensor_x_z", FloatParam, "Sensor +x axis z (lab frame)", default=float(sz)
        )
        self.sensor_x_z: FloatParamHandle

        yx, yy, yz = constants.ANDOR_SENSOR_Y_AXIS_DEFAULT
        self.setattr_param(
            "sensor_y_x", FloatParam, "Sensor +y axis x (lab frame)", default=float(yx)
        )
        self.sensor_y_x: FloatParamHandle
        self.setattr_param(
            "sensor_y_y", FloatParam, "Sensor +y axis y (lab frame)", default=float(yy)
        )
        self.sensor_y_y: FloatParamHandle
        self.setattr_param(
            "sensor_y_z", FloatParam, "Sensor +y axis z (lab frame)", default=float(yz)
        )
        self.sensor_y_z: FloatParamHandle

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

        The grabber sees the fast-kinetics *readout frame*, not raw sensor
        coordinates. Following the convention of
        :class:`~repository.lib.experiment_templates.mixins.andor_imaging.normalised_fast_kinetics_base.NormalisedFKConfig`:
        the first shot (ground port) lands at sensor y minus
        ``fast_kinetics_offset``, and the second shot (excited port) is
        shifted a further ``fast_kinetics_height`` down the readout frame by
        the inter-shot row shift. The *physical* inter-shot motion of the
        cloud is already in the predicted ``excited_y``, so no additional
        shift is applied here.

        Each ROI is clamped to the readout frame, recorded in
        ``roi_clipped``, and degenerate-but-valid if fully off frame.
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
        t1: TInt64,
        t2: TInt64,
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
        t_playback_start_mu: TInt64,
        t_release_mu: TInt64,
    ) -> None:
        """
        Predict the cloud pixel positions at the imaging times and store them
        in ``gnd_x/y``, ``excited_x/y``, ``gnd_multiplicity`` and
        ``excited_multiplicity``.

        Args:
            t1: Live-timeline machine-unit timestamp of the ground-port
                (first fast-kinetics) imaging pulse.
            t2: Live-timeline machine-unit timestamp of the excited-port
                (second fast-kinetics) imaging pulse.
            intent_start_times_mu: Recorded intent event start times,
                *recording-relative* machine units (``core_dma.record``
                resets the timeline cursor to zero).
            intent_durations_mu: Recorded intent event durations in machine
                units.
            intent_kinds: Intent event kinds
                (:mod:`repository.lib.pulse_intent`).
            intent_state_effects: Intent state effects.
            intent_addressed_states: Addressed internal states.
            intent_addressed_m: Addressed momentum classes.
            intent_delta_m: Recoils given to the transferred component.
            num_events: Number of valid entries at the start of the intent
                arrays.
            t_playback_start_mu: Live-timeline timestamp captured immediately
                before the DMA playback starts; recorded events fire at
                ``t_playback_start_mu + t_recorded``.
            t_release_mu: Live-timeline timestamp of the atom release (t=0
                for the trajectory).
        """
        # Slice to the populated entries BEFORE the RPC: the intent buffers are
        # BUFFER_DEPTH (300) long, and marshalling all of them kernel->host on
        # every call costs several ms of timeline slack (enough to underflow
        # the imaging budget). Only num_events entries are valid, so send just
        # those - typically 0 (a plain drop) to a few tens (a launch ladder).
        packed = self._calculate_positions_host(
            t1,
            t2,
            intent_start_times_mu[:num_events],
            intent_durations_mu[:num_events],
            intent_kinds[:num_events],
            intent_state_effects[:num_events],
            intent_addressed_states[:num_events],
            intent_addressed_m[:num_events],
            intent_delta_m[:num_events],
            num_events,
            t_playback_start_mu,
            t_release_mu,
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
        t1_mu: TInt64,
        t2_mu: TInt64,
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
        t_playback_start_mu: TInt64,
        t_release_mu: TInt64,
    ) -> TArray(TInt32, 1):  # pyright: ignore[reportInvalidTypeForm]
        """Host-side predictor: returns ``[gnd_x, gnd_y, exc_x, exc_y,
        gnd_multiplicity, exc_multiplicity]`` as int32."""
        camera = CameraGeometry(
            optical_axis=np.array(
                [
                    self.optical_axis_x.get(),
                    self.optical_axis_y.get(),
                    self.optical_axis_z.get(),
                ]
            ),
            sensor_x_axis=np.array(
                [
                    self.sensor_x_x.get(),
                    self.sensor_x_y.get(),
                    self.sensor_x_z.get(),
                ]
            ),
            sensor_y_axis=np.array(
                [
                    self.sensor_y_x.get(),
                    self.sensor_y_y.get(),
                    self.sensor_y_z.get(),
                ]
            ),
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

        # The recorded intent timestamps are recording-relative; during
        # playback they fire at t_playback_start + t_recorded. Rebase them to
        # seconds since release. The image times are live timestamps.
        t_start_s = trajectory.rebase_record_times_mu(
            intent_start_times_mu[:num_events],
            t_playback_start_mu,
            t_release_mu,
            self.core.ref_period,
        )
        duration_s = (
            np.asarray(intent_durations_mu[:num_events], dtype=np.int64)
            * self.core.ref_period
        )
        t_image_s = trajectory.live_times_to_seconds_since_release(
            [t1_mu, t2_mu], t_release_mu, self.core.ref_period
        )

        # An empty stream (num_events == 0) is handled by predict_port_pixels
        # as pure free fall.
        events = pulse_intent.intent_events_from_arrays(
            t_start_s=t_start_s,
            duration_s=duration_s,
            kinds=intent_kinds[:num_events],
            state_effects=intent_state_effects[:num_events],
            addressed_states=intent_addressed_states[:num_events],
            addressed_m=intent_addressed_m[:num_events],
            delta_m=intent_delta_m[:num_events],
        )

        out = trajectory.predict_port_pixels(
            events,
            t_image_ground_s=float(t_image_s[0]),
            t_image_excited_s=float(t_image_s[1]),
            cfg=cfg,
        )
        gnd = out["ground"]
        exc = out["excited"]

        # NB: no logging in this hot path. It runs as a blocking RPC inside the
        # imaging slack budget, and emitting a log record per shot to the
        # master's (potentially slow) handlers can cost several ms of timeline
        # slack - enough to underflow the first camera trigger. Predicted
        # positions and multiplicities are published on the diagnostics result
        # channels instead (predicted_*_x/y, *_port_multiplicity). A
        # multiplicity of 0 (empty port -> centred on the other port's cloud)
        # or >1 (open interferometer -> centred on the branch mean) is visible
        # there; the ROIs are still placed sensibly in both cases.

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
    Variant of :class:`~.NormalisedFastKineticsBase` that uses
    :class:`~LMTCompensatedCameraConfig` to dynamically reposition the camera
    ROIs based on the trajectory of the atom clouds predicted from the
    recorded pulse intent stream.

    Contract — the experiment base combined with this mixin must provide:

    * ``dma_recording_fragment``: a
      :class:`~repository.lib.fragments.pulse_recorder_and_tracker.PulseDMARecording`
      whose intent buffers describe the recorded sequence (provided by
      :class:`~repository.lib.experiment_templates.dipole_trap_experiment.DipoleTrapWithExperimentBase`).
    * ``get_t_release_mu() -> TInt64`` (``@portable``): the *live-timeline*
      machine-unit timestamp of the atom release (t=0 for the trajectory).
    * ``get_t_playback_start_mu() -> TInt64`` (``@portable``): the
      live-timeline timestamp captured immediately before the DMA playback of
      the recorded sequence starts. Recorded (recording-relative) timestamps
      fire at ``t_playback_start + t_recorded`` during playback.

    ``DipoleTrapWithExperimentBase`` does *not* yet provide the two timebase
    accessors - a red-MOT experiment base providing them is being added in
    parallel. For the dipole path, note that the legacy
    ``t_dipole_beams_off`` is stamped *inside* the DMA recording (so it is
    recording-relative); the live release time it corresponds to is
    ``t_playback_start_mu + t_dipole_beams_off``.

    Diagnostics result channels (pushed exactly once per shot): the predicted
    port positions, the port multiplicities, whether any ROI had to be
    clamped to the readout frame, and the timeline slack before/after the
    prediction RPC (to tune ``roi_prediction_budget``).

    Kernel hooks overridden:

    * :meth:`~get_andor_camera_config_hook`
    * :meth:`~do_imaging_hook_andor`
    """

    def get_andor_camera_config_hook(self) -> AndorCameraConfig:
        f = self.setattr_fragment("andor_camera_config", LMTCompensatedCameraConfig)
        self.andor_camera_config: LMTCompensatedCameraConfig
        return f

    def build_fragment(self):
        super().build_fragment()

        # Re-expose the camera-config tuning params at the experiment level so
        # they can be set/scanned from the dashboard and the submit API (the
        # sub-fragment params are otherwise only reachable at a nested override
        # path). The trap pixel position in particular is source-specific (the
        # red MOT and dipole trap sit at different sensor positions) and needs
        # commissioning per source.
        self.setattr_param_rebind(
            "trap_x_pixel", self.andor_camera_config, "trap_x_pixel"
        )
        self.setattr_param_rebind(
            "trap_y_pixel", self.andor_camera_config, "trap_y_pixel"
        )
        self.setattr_param_rebind("roi_width", self.andor_camera_config, "roi_width")
        self.setattr_param_rebind("roi_height", self.andor_camera_config, "roi_height")

        self.setattr_param(
            "roi_prediction_budget",
            FloatParam,
            "Timeline slack reserved for the ROI prediction RPC",
            # The RPC is warmed up (off-budget) before the timed call, so a few
            # ms is ample. Kept small to minimise the added time-of-flight: the
            # cloud falls during this budget before the first image.
            default=5e-3,
            unit="ms",
            min=0,
        )
        self.roi_prediction_budget: FloatParamHandle

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
        self.setattr_result(
            "prediction_slack_before", FloatChannel, display_hints={"priority": -1}
        )
        self.prediction_slack_before: FloatChannel
        self.setattr_result(
            "prediction_slack_after", FloatChannel, display_hints={"priority": -1}
        )
        self.prediction_slack_after: FloatChannel

    @kernel
    def _predict_atom_positions(self, t1_mu: TInt64, t2_mu: TInt64):
        """Run the host-side ROI prediction for imaging times t1/t2.

        Shared by the warm-up call and the real, budget-timed call in
        :meth:`do_imaging_hook_andor` so the long intent-buffer argument list
        lives in one place.
        """
        self.andor_camera_config.calculate_atom_positions(
            t1=t1_mu,
            t2=t2_mu,
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
            t_playback_start_mu=self.get_t_playback_start_mu(),
            t_release_mu=self.get_t_release_mu(),
        )

    @kernel
    def do_imaging_hook_andor(self):
        # Warm up the prediction RPC path with generous slack BEFORE the timed
        # section. The first prediction call on a fresh ARTIQ worker is slow
        # (host-side imports/JIT and the kernel<->host round-trip the first
        # time), which would otherwise have to be covered by - and so inflate -
        # roi_prediction_budget (and hence the time-of-flight). Running one
        # throwaway prediction here, bracketed by break_realtime so its latency
        # cannot underflow, makes the real timed call below fast. The throwaway
        # result is immediately overwritten by the real call.
        self.core.break_realtime()
        self._predict_atom_positions(now_mu(), now_mu())
        self.core.break_realtime()

        # Pin the first imaging time now, so the wall-clock duration of the
        # prediction RPC cannot shift it: everything below runs inside the
        # slack reserved by roi_prediction_budget.
        t_image_mu = now_mu() + self.core.seconds_to_mu(
            self.roi_prediction_budget.get()
        )
        t2_mu = t_image_mu + self.core.seconds_to_mu(
            self.andor_camera_config.fast_kinetics_time_between_shots.get()
        )

        self.prediction_slack_before.push(
            self.core.mu_to_seconds(now_mu() - self.core.get_rtio_counter_mu())
        )

        self._predict_atom_positions(t_image_mu, t2_mu)

        self.prediction_slack_after.push(
            self.core.mu_to_seconds(now_mu() - self.core.get_rtio_counter_mu())
        )

        # Reprogram the grabber with the freshly predicted ROIs. The writes
        # land in the remaining budget, before the first camera frame.
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

        at_mu(t_image_mu)
        # ARTIQ kernels do not support super(); call the base implementation
        # by name instead
        self.do_imaging_hook_andor_default()


class NormalisedFastKineticsLMTCorrectedMixin(
    NormalisedFastKineticsClockPulseMixin, DynamicROIImagingMixin
):
    """
    :class:`~.DynamicROIImagingMixin` combined with the clock-pulse readout
    of :class:`~.NormalisedFastKineticsClockPulseMixin`.

    This preserves the behaviour existing users (e.g.
    ``repository/LMT/lmt_declarative.py``) relied on from the old
    ``NormalisedFastKineticsLMTCorrectedMixin``: dynamic ROIs from
    :class:`~.DynamicROIImagingMixin` (which wins
    ``do_imaging_hook_andor`` / ``get_andor_camera_config_hook`` in the MRO)
    plus the clock pi pulse after the first fluorescence pulse (the clock
    mixin's ``do_first_pulse``). See :class:`~.DynamicROIImagingMixin` for
    the timebase-accessor contract the experiment base must satisfy.
    """
