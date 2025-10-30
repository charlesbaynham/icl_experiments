import logging

from artiq.coredevice.ad9910 import AD9910
from artiq.coredevice.core import Core
from artiq.language import kernel
from ndscan.experiment import Fragment
from ndscan.experiment.parameters import FloatParam
from ndscan.experiment.parameters import FloatParamHandle
from pyaion.fragments.ad9910_ramper import AD9910Ramper

from repository.lib import constants
from repository.lib.experiment_templates.red_mot_experiment import RedMOTWithExperiment

logger = logging.getLogger(__name__)


class ShelveInBlueMOTMixin(RedMOTWithExperiment):
    """
    Add shelving during blue MOT to protect cold atoms from loss mechanisms
    """

    def build_fragment(self):
        super().build_fragment()

        class _ShelvingFrag(Fragment):
            def build_fragment(self,injection_aom_static_frequency:FloatParamHandle ):
                self.setattr_device("core")
                self.core: Core

                self.injection_aom_static_frequency = injection_aom_static_frequency


                # Fast ramping of the AD9910 controlling the injection AOM
                self.setattr_fragment(
                    "injection_aom_ramper",
                    AD9910Ramper,
                    "urukul9910_aom_doublepass_689_red_injection",
                )
                self.injection_aom_ramper: AD9910Ramper

                self.setattr_param(
                    "ramp_frequency",
                    FloatParam,
                    "689 injection AOM ramp frequency during blue MOT",
                    unit="kHz",
                    default=constants.RED_INJECTION_AOM_RAMP_FREQUENCY,
                )
                self.ramp_frequency: FloatParamHandle


                self.ramp_rate = 0.0

            @kernel
            def device_setup(self) -> None:
                # Precalculate the ramp rate required to get the requested modulation frequency
                self.ramp_rate = abs(
                    (self.ramp_lower_detuning.get() - self.ramp_upper_detuning.get())
                    * self.ramp_frequency.get()
                )

            @kernel
            def before_blue_mot_hook(self):
                self.injection_aom_ramper.start_ramp(
                    self.ramp_rate,
                    self.injection_aom_static_frequency.get() + 0.0e6,
                    self.injection_aom_static_frequency.get() + 3e6,
                    2, # negative saw
                )

                self.red_mot.  # FIXME WIP
