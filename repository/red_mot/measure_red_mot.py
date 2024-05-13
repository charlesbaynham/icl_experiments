import logging

from artiq.experiment import delay
from artiq.experiment import kernel
from artiq.experiment import now_mu
from artiq.experiment import parallel
from ndscan.experiment.entry_point import make_fragment_scan_exp

from repository.lib.fragments.red_mot.red_mot_experiment import RedMOTBase
from repository.lib.fragments.red_mot.red_mot_experiment import RedMOTWithExperiment
from repository.lib.fragments.red_mot.red_mot_mixins.single_andor_image import (
    SingleAndorImage,
)


logger = logging.getLogger(__name__)


class MeasureBBRedMOTFrag(RedMOTBase):
    @kernel
    def run_once(self):
        self.core.break_realtime()
        self._from_start_to_end_of_broadband_mot()
        self._expand_and_image()
        self._save_data()

    @kernel
    def _expand_and_image(self):
        self.red_mot.red_beam_controller.turn_off_mot_beams()

        delay(self.expansion_time.get())

        with parallel:
            self.andor_camera_control.trigger(
                exposure=self.fluorescence_pulse.fluorescence_pulse_duration.get(),
                control_shutter=True,
            )
            self.fluorescence_pulse.do_imaging_pulse()
            self.camera_interface.trigger()

        # Turn the fields back to defaults so eddy currents are gone by the next shot
        delay(1e-3)
        self.blue_3d_mot.enable_mot_fields()

    @kernel
    def _save_data(self):
        "Consume all slack and save the photos"
        self.core.wait_until_mu(now_mu())
        self.camera_interface.save_data()
        sums = [0]
        means = [0.0]
        self.andor_camera_control.readout_ROIs(
            sums,
            means,
            timeout_mu=self.core.get_rtio_counter_mu() + self.core.seconds_to_mu(1.0),
        )
        self.andor_sum.push(sums[0])
        self.andor_mean.push(means[0])


class MeasureNarrowbandMOTFrag(SingleAndorImage, RedMOTWithExperiment):
    @kernel
    def do_spectroscopy_hook(self):
        # No spectroscopy needed - just do nothing and move straight to imaging
        pass


MeasureBBRedMOT = make_fragment_scan_exp(MeasureBBRedMOTFrag)
MeasureNarrowbandRedMOT = make_fragment_scan_exp(
    MeasureNarrowbandMOTFrag, max_rtio_underflow_retries=0
)
