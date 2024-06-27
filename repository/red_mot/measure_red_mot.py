import logging

from artiq.experiment import delay
from artiq.experiment import kernel
from artiq.experiment import now_mu
from artiq.experiment import parallel
from ndscan.experiment import FloatChannel
from ndscan.experiment.entry_point import make_fragment_scan_exp

from repository.lib.fragments.cameras.andor_camera import AndorCameraControl
from repository.lib.fragments.red_mot.red_mot_experiment import RedMOTBase
from repository.lib.fragments.red_mot.red_mot_experiment import RedMOTWithExperiment
from repository.lib.fragments.red_mot.red_mot_mixins.bg_corrected_andor_image import (
    BGCorrectedAndorImage,
)
from repository.lib.fragments.red_mot.red_mot_mixins.constant_lattice import (
    ConstantLatticeMixin,
)
from repository.lib.fragments.red_mot.red_mot_mixins.flir_measurement import (
    FLIRMeasurementMixin,
)
from repository.lib.fragments.red_mot.red_mot_mixins.single_andor_image import (
    SingleAndorImage,
)

logger = logging.getLogger(__name__)


class MeasureBBRedMOTFrag(RedMOTBase):
    def build_fragment(self):
        super().build_fragment()

        self._setup_andor()

    def _setup_andor(self):
        """
        Setup the Andor camera

        This is a method so that children classes can override it
        """
        self.setattr_fragment("andor_camera_control", AndorCameraControl)
        self.andor_camera_control: AndorCameraControl

        self.setattr_result("andor_sum", FloatChannel, display_hints={"priority": -1})
        self.setattr_result("andor_mean", FloatChannel)
        self.andor_sum: FloatChannel
        self.andor_mean: FloatChannel

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


class _MeasureNarrowbandMOTFrag(ConstantLatticeMixin, RedMOTWithExperiment):
    def build_fragment(self):
        super().build_fragment()

        # Remove unused parameters
        self.override_param("delay_after_spectroscopy", 0)
        self.override_param("spectroscopy_field_gradient", 0)

    @kernel
    def do_spectroscopy_hook(self):
        # No spectroscopy needed - just do nothing and move straight to imaging
        pass

    def build_fragment(self):
        super().build_fragment()

        # Disable unused params
        for p in ["delay_after_spectroscopy"]:
            self.override_param(p, 0)


class MeasureNarrowbandMOTFrag(
    FLIRMeasurementMixin, SingleAndorImage, _MeasureNarrowbandMOTFrag
):
    """
    Make a narrowband MOT, image with the ANDOR and leave lattice light on
    """

    pass


class MeasureNarrowbandMOTBGCorrectedFrag(
    BGCorrectedAndorImage, _MeasureNarrowbandMOTFrag
):
    """
    Make a narrowband MOT, image twice for BG subtraction with the ANDOR and leave lattice light on
    """

    pass


MeasureBBRedMOT = make_fragment_scan_exp(MeasureBBRedMOTFrag)
MeasureNarrowbandRedMOT = make_fragment_scan_exp(MeasureNarrowbandMOTFrag)

MeasureNarrowbandRedMOTBGCorrected = make_fragment_scan_exp(
    MeasureNarrowbandMOTBGCorrectedFrag
)
