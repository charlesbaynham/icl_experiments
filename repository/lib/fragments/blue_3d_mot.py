import logging

from artiq.coredevice.core import Core
from artiq.experiment import delay
from artiq.experiment import delay_mu
from artiq.experiment import kernel
from artiq.experiment import ns
from artiq.experiment import TFloat
from artiq.experiment import TInt32
from artiq.experiment import TInt64
from artiq.experiment import TList
from ndscan.experiment import Fragment

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
            "blue_2dmot_A",
            "blue_2dmot_B",
        ]:
            beam_info = constants.AOM_BEAMS[beam_name]
            self.setattr_fragment(
                f"{beam_name}_setter", ControlBeamWithoutCoolingAOM, beam_info=beam_info
            )

        self.blue_push_beam_setter: ControlBeamWithoutCoolingAOM
        self.blue_3dmot_radial_setter: ControlBeamWithoutCoolingAOM
        self.blue_3dmot_axialplus_setter: ControlBeamWithoutCoolingAOM
        self.blue_3dmot_axialminus_setter: ControlBeamWithoutCoolingAOM

        self.blue_2dmot_A_setter: ControlBeamWithoutCoolingAOM
        self.blue_2dmot_B_setter: ControlBeamWithoutCoolingAOM

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
    def turn_on_2d_mot_beams(self):
        """
        Turn on the 2D mot beams using the AOM+shutter sequence
        from :class:`.ControlBeamWithoutCoolingAOM`
        """
        self.blue_2dmot_A_setter.turn_beam_on()
        delay(20 * ns)
        self.blue_2dmot_B_setter.turn_beam_on()
        delay(20 * ns)

    @kernel
    def turn_off_2d_mot_beams(self):
        """
        Turn off the 2D mot beams using the AOM+shutter sequence
        from :class:`.ControlBeamWithoutCoolingAOM`
        """
        self.blue_2dmot_A_setter.turn_beam_off()
        delay(20 * ns)
        self.blue_2dmot_B_setter.turn_beam_off()
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
