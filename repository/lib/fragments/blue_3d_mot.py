import logging

from artiq.coredevice.core import Core
from artiq.experiment import delay_mu
from artiq.experiment import kernel
from artiq.experiment import TFloat
from artiq.experiment import TInt32
from artiq.experiment import TInt64
from artiq.experiment import TList
from ndscan.experiment import Fragment
from pyaion.fragments.beam_setter import ControlBeamsWithoutCoolingAOM

import repository.lib.constants as constants
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

        self.setattr_fragment(
            "all_mot_beams_setter",
            ControlBeamsWithoutCoolingAOM,
            beam_infos=[
                constants.AOM_BEAMS["blue_push_beam"],
                constants.AOM_BEAMS["blue_3dmot_radial"],
                constants.AOM_BEAMS["blue_3dmot_axialplus"],
                constants.AOM_BEAMS["blue_3dmot_axialminus"],
                constants.AOM_BEAMS["blue_2dmot_A"],
                constants.AOM_BEAMS["blue_2dmot_B"],
            ],
        )
        self.all_mot_beams_setter: ControlBeamsWithoutCoolingAOM

        self.setattr_fragment(
            "mot_3d_beams_setter",
            ControlBeamsWithoutCoolingAOM,
            beam_infos=[
                constants.AOM_BEAMS["blue_3dmot_radial"],
                constants.AOM_BEAMS["blue_3dmot_axialplus"],
                constants.AOM_BEAMS["blue_3dmot_axialminus"],
            ],
        )
        self.mot_3d_beams_setter: ControlBeamsWithoutCoolingAOM

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
    def turn_on_3d_and_2d_beams(self):
        self.all_mot_beams_setter.turn_beams_on()

    @kernel
    def turn_off_3d_and_2d_beams(self):
        self.all_mot_beams_setter.turn_beams_off()

    @kernel
    def turn_on_3d_beams(self):
        self.mot_3d_beams_setter.turn_beams_on()

    @kernel
    def turn_off_3d_beams(self):
        self.mot_3d_beams_setter.turn_beams_off()


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
