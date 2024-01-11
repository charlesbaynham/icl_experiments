import logging

from artiq.experiment import delay
from artiq.experiment import kernel
from ndscan.experiment.entry_point import make_fragment_scan_exp

from repository.lib.fragments.triple_imaging_kinetics import TripleImageMOTFrag

logger = logging.getLogger(__name__)


class AbsorptionRedMOT(TripleImageMOTFrag):
    """
    Image red MOT with absorption
    """

    @kernel
    def do_spectroscopy_hook(self):
        pass

    def build_fragment(self):
        super().build_fragment()

        # Set the MOT field to off before the "spectroscopy" (i.e. imaging) starts
        self.override_param("spectroscopy_field_gradient", 0.0)

    @kernel
    def do_third_pulse(self, andor_exposure):
        # Trigger the third time without any fluorescence
        delay(-0.5 * andor_exposure)
        self.andor_camera_control.trigger(
            exposure=andor_exposure,
            control_shutter=False,
        )
        delay(0.5 * andor_exposure)


AbsorptionRedMOTExp = make_fragment_scan_exp(AbsorptionRedMOT)
