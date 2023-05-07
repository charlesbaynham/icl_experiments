import logging
import time
from typing import List
from typing import Tuple

import aravis
import numpy as np
from aravis import Camera
from artiq.coredevice.core import Core
from artiq.experiment import delay
from artiq.experiment import delay_mu
from artiq.experiment import host_only
from artiq.experiment import kernel
from artiq.experiment import ns
from artiq.experiment import rpc
from artiq.experiment import TFloat
from artiq.experiment import TInt32
from artiq.experiment import TInt64
from artiq.experiment import TList
from ndscan.experiment import Fragment
from ndscan.experiment.parameters import FloatParam
from ndscan.experiment.parameters import FloatParamHandle
from ndscan.experiment.parameters import IntParam
from ndscan.experiment.parameters import IntParamHandle

import repository.lib.constants as constants
from repository.lib.fragments.beam_setters import ControlBeamWithoutCoolingAOM
from repository.lib.fragments.beam_setters import SetBeamsToDefaults
from repository.lib.fragments.read_adc import ReadSUServoADC

logger = logging.getLogger(__name__)


BLUE_3D_MOT_BEAMS = [
    "blue_push_beam",
    "blue_2dmot_A",
    "blue_2dmot_B",
    "blue_3dmot_radial",
    "blue_3dmot_axialplus",
    "blue_3dmot_axialminus",
    "blue_injection",
]


class Blue3DMOTFrag(Fragment):
    """
    Methods for making and controlling the blue 3D MOT
    """

    def build_fragment(self):
        self.setattr_device("core")
        self.core: Core

        self.setattr_fragment(
            "all_beam_default_setter",
            SetBeamsToDefaults,
            beams_to_enable=BLUE_3D_MOT_BEAMS,
        )
        self.all_beam_default_setter: SetBeamsToDefaults

        # Give us access to on/off methods for the push beam and the 3D MOT beams
        for beam_name in [
            "blue_push_beam",
            "blue_3dmot_radial",
            "blue_3dmot_axialplus",
            "blue_3dmot_axialminus",
        ]:
            beam_info = constants.AOM_BEAMS[beam_name]
            self.setattr_fragment(
                f"{beam_name}_setter", ControlBeamWithoutCoolingAOM, beam_info=beam_info
            )

        self.blue_push_beam_setter: ControlBeamWithoutCoolingAOM
        self.blue_3dmot_radial_setter: ControlBeamWithoutCoolingAOM
        self.blue_3dmot_axialplus_setter: ControlBeamWithoutCoolingAOM
        self.blue_3dmot_axialminus_setter: ControlBeamWithoutCoolingAOM

    @kernel
    def enable_mot_beams(self):
        """
        Immediately turn on all beams related to the 3D blue MOT

        This method does not advance the timeline and does not
        respect beam shutter delays - it just turns everything
        on immediately.
        """
        self.all_beam_default_setter.turn_on_all()

    @kernel
    def turn_on_push_beam(self):
        """
        Turn on the push beam using the AOM+shutter sequence
        from :class:`.ControlBeamWithoutCoolingAOM`
        """
        self.blue_push_beam_setter.turn_beam_on()
        delay(20 * ns)

    @kernel
    def turn_off_push_beam(self):
        """
        Turn off the push beam using the AOM+shutter sequence
        from :class:`.ControlBeamWithoutCoolingAOM`
        """
        self.blue_push_beam_setter.turn_beam_off()
        delay(20 * ns)

    @kernel
    def turn_on_3d_mot_beams(self):
        """
        Turn on the mot beams using the AOM+shutter sequence
        from :class:`.ControlBeamWithoutCoolingAOM`
        """
        self.blue_3dmot_radial_setter.turn_beam_on()
        delay(20 * ns)
        self.blue_3dmot_axialplus_setter.turn_beam_on()
        delay(20 * ns)
        self.blue_3dmot_axialminus_setter.turn_beam_on()
        delay(20 * ns)

    @kernel
    def turn_off_3d_mot_beams(self):
        """
        Turn off the mot beams using the AOM+shutter sequence
        from :class:`.ControlBeamWithoutCoolingAOM`
        """
        self.blue_3dmot_radial_setter.turn_beam_off()
        delay(20 * ns)
        self.blue_3dmot_axialplus_setter.turn_beam_off()
        delay(20 * ns)
        self.blue_3dmot_axialminus_setter.turn_beam_off()
        delay(20 * ns)


class MOTPhotodiodeMeasurement(Fragment):
    def build_fragment(self):
        self.setattr_device("core")
        self.core: Core

        photodiode_suservo_name, photodiode_suservo_channel = self.get_device_db()[
            "mot_photodiode_sampler_config"
        ]

        # Load the ADC utility subfragment
        self.setattr_fragment(
            "adc_reader",
            ReadSUServoADC,
            self.get_device(photodiode_suservo_name),
            photodiode_suservo_channel,
        )
        self.adc_reader: ReadSUServoADC

    @kernel
    def measure_MOT_fluorescence(
        self, num_points: TInt32, delay_between_points_mu: TInt64, data: TList(TFloat)
    ) -> None:
        """
        Read the flourescence out into an array.

        You must pass an array of floats with size <num_points> to `data`.
        """

        for i in range(num_points):
            data[i] = self.adc_reader.read_adc()
            delay_mu(delay_between_points_mu)


class Chamber2Camera:
    def __init__(self, num_images, exposure_us, delay_ms):
        if delay_ms < 20:
            raise ValueError(
                "The camera cannot support a frame rate faster than 20ms per frame"
            )

        self.cam = Camera(
            "FLIR-Blackfly S BFS-PGE-50S5M-22018873", loglevel=logging.INFO
        )
        self.cam.set_frame_rate(1 / (1e-3 * delay_ms))
        self.cam.set_exposure_time(exposure_us)

        self._num_images = num_images
        self._buffer_depth = num_images + 10
        self._per_image_time = max([1e-6 * exposure_us, 1e-3 * delay_ms])

    def capture_frames(self) -> List[Tuple[int, np.array]]:
        self.cam.start_acquisition_continuous(nb_buffers=self._buffer_depth)

        out = []
        while True:
            time.sleep(self._per_image_time)

            ts, frame = self.cam.try_pop_frame(True)
            if ts is not None:
                out.append((ts, frame))

            if len(out) == self._num_images:
                break

        self.cam.stop_acquisition()

        return out


class MOTCameraMeasurement(Fragment):
    def build_fragment(self):
        self.setattr_device("core")
        self.core: Core

        self.setattr_param(
            "exposure",
            FloatParam,
            description="Exposure per image",
            default=1e-3,
            unit="us",
            step=1,
        )
        self.exposure: FloatParamHandle

        self.setattr_param(
            "image_delay",
            FloatParam,
            description="Delay between startring aquisition of frames",
            default=20e-3,
            min=20e-3,
            unit="ms",
            step=1,
        )
        self.image_delay: FloatParamHandle

        self.setattr_param(
            "number_images",
            IntParam,
            description="Number of images to take",
            default=100,
            min=1,
            step=1,
        )
        self.number_images: IntParamHandle

    def host_setup(self):
        self.camera_driver = Chamber2Camera(
            num_images=self.number_images.get(),
            exposure_us=1e6 * self.exposure.get(),
            delay_ms=1e3 * self.image_delay.get(),
        )
        self.images = None
        return super().host_setup()

    @rpc
    def start_camera_measurement(self):
        """
        Start measuring images using pre-defined camera settings

        When finished, images will be available via :meth:`.get_images()`
        """
        self.images = self.camera_driver.capture_frames()

    @host_only
    def get_images(self):
        if self.images is None:
            raise RuntimeError("Images have not yet been aquired")

        return self.images
