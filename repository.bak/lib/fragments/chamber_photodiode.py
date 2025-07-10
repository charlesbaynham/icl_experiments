"""
Fragment to read a photodiode that measures the MOT fluorescence. This is no
longer in the system (2023-09-12) so this code is left in case it's useful
later.
"""

import logging

from artiq.coredevice.core import Core
from artiq.experiment import TFloat
from artiq.experiment import TInt32
from artiq.experiment import TInt64
from artiq.experiment import TList
from artiq.language import delay_mu
from artiq.language import kernel
from ndscan.experiment import Fragment

from device_db_config import get_configuration_from_db
from repository.lib.fragments.read_adc import ReadSUServoADC

logger = logging.getLogger(__name__)


class _MOTPhotodiodeMeasurement(Fragment):
    def build_fragment(self):
        self.setattr_device("core")
        self.core: Core

        photodiode_suservo_channel = get_configuration_from_db(
            "mot_photodiode_sampler_config"
        )

        # Load the ADC utility subfragment
        self.setattr_fragment(
            "adc_reader",
            ReadSUServoADC,
            self.get_device(photodiode_suservo_channel),
        )
        self.adc_reader: ReadSUServoADC

    @kernel
    def measure_MOT_fluorescence(
        self, num_points: TInt32, delay_between_points_mu: TInt64, data: TList(TFloat)
    ) -> None:
        """
        Read the fluorescence out into an array.

        You must pass an array of floats with size <num_points> to `data`.
        """

        for i in range(num_points):
            data[i] = self.adc_reader.read_adc()
            delay_mu(delay_between_points_mu)
