import logging

from artiq.experiment import delay
from artiq.experiment import kernel
from ndscan.experiment.entry_point import make_fragment_scan_exp
from ndscan.experiment.result_channels import FloatChannel

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

        # These aren't used, so remove them from the interface
        self.override_param("spectroscopy_pulse_time", 0.0)
        self.override_param("spectroscopy_pulse_aom_detuning", 0.0)
        self.override_param("spectroscopy_pulse_aom_amplitude", 0.0)

        self.setattr_result("absorption", FloatChannel)
        self.absorption: FloatChannel

    @kernel
    def do_triple_image(self):
        andor_exposure = 2 * self.fluorescence_pulse.fluorescence_pulse_duration.get()

        # Image ground state atoms
        self.do_first_pulse(andor_exposure)

        # Image excited state atoms
        delay(self.delay_between_fluoresence_pulses.get())
        self.do_second_pulse(andor_exposure)

        # # Take background measurement
        # delay(self.delay_before_background_pulse.get())
        # self.do_third_pulse_without_laser(andor_exposure)

        # # Repeat the third pulse since the camera is set up for 2x images
        # delay(self.delay_before_background_pulse.get())
        # self.do_third_pulse_without_laser(andor_exposure)

    @kernel
    def do_third_pulse_without_laser(self, andor_exposure):
        # Trigger the third time without any fluorescence
        delay(-0.5 * andor_exposure)
        self.andor_camera_control.trigger(
            exposure=andor_exposure,
            control_shutter=False,
        )
        delay(0.5 * andor_exposure)

    @kernel
    def after_sequence_hook(self, sum0, sum1, sum2, mean0, mean1, mean2):
        self.absorption.push(sum1 - sum0)


AbsorptionRedMOTExp = make_fragment_scan_exp(AbsorptionRedMOT)
