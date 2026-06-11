import logging

import numpy as np
from artiq.language import TArray
from artiq.language import TInt32
from artiq.language import TInt64
from artiq.language import TList
from artiq.language import kernel
from artiq.language import now_mu
from artiq.language import rpc
from ndscan.experiment.parameters import FloatParam
from ndscan.experiment.parameters import FloatParamHandle
from ndscan.experiment.parameters import IntParam
from ndscan.experiment.parameters import IntParamHandle

from repository.lib import constants
from repository.lib.experiment_templates.dipole_trap_experiment import (
    DipoleTrapWithExperimentBase,
)
from repository.lib.experiment_templates.mixins.andor_imaging.normalised_fast_kinetics_base import (
    NormalisedFastKineticsClockPulseMixin,
)
from repository.lib.fragments.cameras.andor_camera import AndorCameraConfig
from repository.lib.fragments.cameras.andor_camera import FastKineticsCameraConfig
from repository.lib.physics.ballistic import BallisticConfig
from repository.lib.physics.ballistic import CameraGeometry
from repository.lib.physics.ballistic import predict_positions_from_mu

logger = logging.getLogger(__name__)


class LMTCompensatedCameraConfig(FastKineticsCameraConfig):
    """
    Andor camera configuration that dynamically repositions ROIs based on
    the ballistic trajectory of the atom cloud.

    Call :meth:`calculate_atom_positions` once between DMA playback and the
    first fluorescence pulse. It RPC-calls the host-side ballistic predictor
    which fills ``gnd_x/y`` and ``excited_x/y``; :meth:`get_rois` then builds
    ROIs centred on those pixel positions.

    Camera geometry is fully configurable via ndscan parameters so that
    small unknown tilts can be corrected without code changes.
    """

    num_andor_images = 4
    num_images_per_series = 2
    num_grabber_rois = 2
    num_grabber_readouts = 2
    fast_kinetics_num_shots = 2

    fast_kinetics_height_default = constants.ANDOR_FAST_KINETICS_HEIGHT
    fast_kinetics_offset_default = constants.ANDOR_FAST_KINETICS_OFFSET

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
            default=int((constants.ANDOR_ROI_X0 + constants.ANDOR_ROI_X1) // 2),
            min=0,
            max=constants.ANDOR_CAMERA_FACTS["sensor_width"],
        )
        self.trap_x_pixel: IntParamHandle

        self.setattr_param(
            "trap_y_pixel",
            IntParam,
            "Pixel y coordinate of the trap centre",
            default=int((constants.ANDOR_ROI_Y0 + constants.ANDOR_ROI_Y1) // 2),
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

        # Kernel variables — pixel positions filled by calculate_atom_positions
        self.gnd_x = 0
        self.gnd_y = 0
        self.excited_x = 0
        self.excited_y = 0

        # Cache sensor dimensions as kernel invariants
        self.andor_sensor_width = constants.ANDOR_CAMERA_FACTS["sensor_width"]
        self.andor_sensor_height = constants.ANDOR_CAMERA_FACTS["sensor_height"]
        self.kernel_invariants = getattr(self, "kernel_invariants", set())
        self.kernel_invariants.add("andor_sensor_width")
        self.kernel_invariants.add("andor_sensor_height")

    # ── ROI calculation ───────────────────────────────────────────────────────

    @kernel
    def get_rois(self):
        half_width = self.roi_width.get() // 2
        half_height = self.roi_height.get() // 2

        self.roi_buffer[0][0] = max(0, self.gnd_x - half_width)
        self.roi_buffer[0][1] = max(0, self.gnd_y - half_height)
        self.roi_buffer[0][2] = min(self.andor_sensor_width, self.gnd_x + half_width)
        self.roi_buffer[0][3] = min(
            2 * self.andor_sensor_height,
            self.gnd_y + half_height,
        )

        self.roi_buffer[1][0] = max(0, self.excited_x - half_width)
        self.roi_buffer[1][1] = max(0, self.excited_y - half_height)
        self.roi_buffer[1][2] = min(
            self.andor_sensor_width, self.excited_x + half_width
        )
        self.roi_buffer[1][3] = min(
            2 * self.andor_sensor_height,
            self.excited_y + half_height,
        )

        return self.roi_buffer

    def host_setup(self):
        super().host_setup()
        self.roi_buffer = np.zeros((self.num_grabber_rois, 4), dtype=np.int32)
        # Initialise gnd/excited to the trap centre so that get_rois() works
        # even if calculate_atom_positions has never been called.
        self.gnd_x = int(self.trap_x_pixel.get())
        self.gnd_y = int(self.trap_y_pixel.get())
        self.excited_x = self.gnd_x
        self.excited_y = self.gnd_y

    # ── Ballistic predictor ───────────────────────────────────────────────────

    @kernel
    def calculate_atom_positions(
        self,
        t1: TInt64,
        t2: TInt64,
        pulse_start_times: TList(TInt64),
        pulse_durations: TList(TInt64),
        pulse_directions: TList(TInt32),
        num_pulses: TInt32,
        t_zero_mu: TInt64,
    ) -> None:
        """
        Calculate the atom cloud pixel positions at imaging times t1 and t2
        and store them in ``gnd_x/y`` and ``excited_x/y``.

        Parameters
        ----------
        t1, t2:
            Machine-unit timestamps for the ground-state and excited-state
            imaging pulses respectively.
        pulse_start_times:
            Pre-allocated array of clock pulse start timestamps (machine units).
        pulse_durations:
            Pre-allocated array of clock pulse durations (machine units).
        pulse_directions:
            Pre-allocated integer array where 1 means up and 0 means down.
        num_pulses:
            Number of valid entries at the start of the pulse arrays.
        t_zero_mu:
            Machine-unit timestamp of atom release (the dipole trap turn-off).
        """
        packed = self._calculate_positions_host(
            t1,
            t2,
            pulse_start_times,
            pulse_durations,
            pulse_directions,
            num_pulses,
            t_zero_mu,
        )
        self.gnd_x = packed[0]
        self.gnd_y = packed[1]
        self.excited_x = packed[2]
        self.excited_y = packed[3]

    @rpc
    def _calculate_positions_host(
        self,
        t1_mu: TInt64,
        t2_mu: TInt64,
        pulse_start_times_mu: TList(TInt64),
        pulse_durations_mu: TList(TInt64),
        pulse_directions: TList(TInt32),
        num_pulses: TInt32,
        t_zero_mu: TInt64,
    ) -> TArray(TInt32, 1):
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
        out = predict_positions_from_mu(
            site_offset_m=np.zeros(3),
            initial_velocity_m_per_s=np.zeros(3),
            pulse_start_times_mu=np.asarray(
                pulse_start_times_mu[:num_pulses], dtype=np.int64
            ),
            pulse_durations_mu=np.asarray(
                pulse_durations_mu[:num_pulses], dtype=np.int64
            ),
            pulse_is_up=np.asarray(pulse_directions[:num_pulses], dtype=bool),
            image_times_mu=np.asarray([t1_mu, t2_mu], dtype=np.int64),
            t_zero_mu=int(t_zero_mu),
            ref_period_s=self.core.ref_period,
            cfg=cfg,
        )
        return np.array(
            [
                int(round(out["ground"][0, 0])),
                int(round(out["ground"][0, 1])),
                int(round(out["excited"][1, 0])),
                int(round(out["excited"][1, 1])),
            ],
            dtype=np.int32,
        )


class NormalisedFastKineticsLMTCorrectedMixin(
    NormalisedFastKineticsClockPulseMixin, DipoleTrapWithExperimentBase
):
    """
    Variant of :class:`~.NormalisedFastKineticsClockPulseMixin` that uses
    :class:`~LMTCompensatedCameraConfig` to dynamically reposition the camera
    ROIs based on the ballistic trajectory of the atom cloud.

    Must be combined with a class that provides:

    * ``dma_recording_fragment`` (from :class:`~DipoleTrapWithExperimentBase`)
    * ``t_dipole_beams_off`` (from :class:`~ClockShelvingAndClearoutDipoleTrapMixin`
      or :class:`~repository.lib.experiment_templates.mixins.declarative_lmt.DeclarativeLMTBase`)

    Kernel hooks overridden:

    * :meth:`~get_andor_camera_config_hook`
    * :meth:`~do_imaging_hook_andor`
    """

    def get_andor_camera_config_hook(self) -> AndorCameraConfig:
        f = self.setattr_fragment("andor_camera_config", LMTCompensatedCameraConfig)
        self.andor_camera_config: LMTCompensatedCameraConfig
        return f

    @kernel
    def do_imaging_hook_andor(self):
        t_zero_mu = self.t_dipole_beams_off
        t1_mu = now_mu()
        t2_mu = t1_mu + self.core.seconds_to_mu(
            self.andor_camera_config.fast_kinetics_time_between_shots.get()
        )

        self.andor_camera_config.calculate_atom_positions(
            t1=t1_mu,
            t2=t2_mu,
            pulse_start_times=self.dma_recording_fragment._pulse_record_start_times_mu,
            pulse_durations=self.dma_recording_fragment._pulse_record_durations_mu,
            pulse_directions=self.dma_recording_fragment._pulse_record_directions,
            num_pulses=self.dma_recording_fragment._pulse_record_num_pulses,
            t_zero_mu=t_zero_mu,
        )

        # ARTIQ kernels do not support super(); call the base implementation
        # by name instead
        self.do_imaging_hook_andor_default()
