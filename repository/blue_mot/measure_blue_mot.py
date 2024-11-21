import logging

from artiq.coredevice.core import Core
from artiq.experiment import delay
from artiq.experiment import kernel
from artiq.experiment import now_mu
from ndscan.experiment import ExpFragment
from ndscan.experiment import OnlineFit
from ndscan.experiment.entry_point import make_fragment_scan_exp
from ndscan.experiment.parameters import BoolParam
from ndscan.experiment.parameters import BoolParamHandle
from ndscan.experiment.parameters import FloatParam
from ndscan.experiment.parameters import FloatParamHandle

from repository.lib.fragments.blue_3d_mot import Blue3DMOTFrag
from repository.lib.fragments.cameras.dual_camera_measurer import BGCorrectedMeasurement
from repository.lib.fragments.cameras.dual_camera_measurer import DualCameraMeasurement
from repository.lib.fragments.fluorescence_pulse import ImagingFluorescencePulse

logger = logging.getLogger(__name__)


class _MeasureBlueMOTFrag(ExpFragment):
    def build_fragment(self):
        self.setattr_device("core")
        self.core: Core

        self.setattr_fragment("mot_controller", Blue3DMOTFrag, manual_init=True)
        self.mot_controller: Blue3DMOTFrag

        self.setattr_param_rebind(
            "mot_loading_time", self.mot_controller, "loading_time"
        )
        self.mot_loading_time: FloatParamHandle

        self.setattr_param(
            "delay_between_points",
            FloatParam,
            "Delay between measurements",
            default=0,
            min=0,
            unit="s",
        )
        self.delay_between_points: FloatParamHandle

        self.setattr_param(
            "clearout",
            BoolParam,
            "Clear out atoms between shots",
            default="True",
        )
        self.clearout: BoolParamHandle

        self.setattr_param(
            "mot_hold_time",
            FloatParam,
            "Time to hold the MOT after loading",
            default=0,
            min=0,
            unit="ms",
        )
        self.mot_hold_time: FloatParamHandle

        self.first_run = True

    @kernel
    def _take_data(self, loading_time):
        raise NotImplementedError

    @kernel
    def run_once(self):
        self.core.break_realtime()

        if self.first_run or self.clearout.get():
            self.first_run = False

            self.mot_controller.init()
            self.mot_controller.enable_mot_fields()
            self.mot_controller.clear_ch2()

        # Delay long enough that we can write shutter closures into the past
        delay(self.mot_controller.mot_all_beam_setter.get_longest_shutter_delay())

        self._before_start_load_hook()

        # Load MOT and start measuring signal immediately
        if self.clearout.get():
            self.mot_controller.turn_on_all_beams()
        else:
            # If clearout was not requested, we'll not change the AOM levels
            # unless this is called at some point so do so now
            self.mot_controller.all_beam_default_setter.turn_on_all(light_enabled=True)

        self._take_data(self.mot_loading_time.get())

        delay(self.delay_between_points.get())
        self.core.wait_until_mu(now_mu())

    @kernel
    def _before_start_load_hook(self):
        pass


class MeasureBlueMOTWithCameraFrag(_MeasureBlueMOTFrag):
    def build_fragment(self):
        self.setattr_fragment(
            "dual_cameras", DualCameraMeasurement, hardware_trigger=True
        )
        self.dual_cameras: DualCameraMeasurement

        self.setattr_param_rebind(
            "exposure",
            self.dual_cameras,
            "exposure_horiz",
            description="Camera exposures",
        )
        self.exposure: FloatParamHandle

        self.dual_cameras.bind_param("exposure_vert", self.exposure)

        super().build_fragment()

    def get_default_analyses(self):
        super_analysis = super().get_default_analyses()

        return super_analysis + [
            OnlineFit(
                "exponential_decay",
                data={
                    "x": self.mot_loading_time,
                    "y": self.dual_cameras.image_vertical_mean,
                },
            )
        ]

    @kernel
    def _take_data(self, loading_time):
        delay(loading_time)

        self.dual_cameras.trigger()

        self.core.wait_until_mu(now_mu())

        self.dual_cameras.save_data()


class MeasureBlueMOTBGCorrectedFrag(_MeasureBlueMOTFrag):
    def build_fragment(self):
        self.setattr_fragment(
            "bg_corrected_measurement", BGCorrectedMeasurement, hardware_trigger=True
        )
        self.bg_corrected_measurement: BGCorrectedMeasurement

        self.setattr_param_rebind(
            "exposure",
            self.bg_corrected_measurement,
            "exposure_horiz",
            description="Camera exposures",
        )
        self.exposure: FloatParamHandle

        self.bg_corrected_measurement.bind_param("exposure_vert", self.exposure)

        super().build_fragment()

    def get_default_analyses(self):
        super_analysis = super().get_default_analyses()

        return super_analysis + [
            OnlineFit(
                "exponential_decay",
                data={
                    "x": self.mot_loading_time,
                    "y": self.bg_corrected_measurement.image_vertical_mean,
                },
            )
        ]

    @kernel
    def _take_data(self, loading_time):
        delay(loading_time)

        self.mot_controller.turn_off_push_beam()
        delay(self.mot_hold_time.get())
        self.bg_corrected_measurement.trigger_signal()

        self.mot_controller.chamber_2_field_setter.set_mot_gradient(0.0)

        delay(400e-3)

        self.bg_corrected_measurement.trigger_background()

        delay(10e-3)

        self.core.wait_until_mu(now_mu())

        self.bg_corrected_measurement.save_data()


class MeasureBlueMOTWithExpansionFrag(_MeasureBlueMOTFrag):
    def build_fragment(self):
        self.setattr_fragment(
            "dual_cameras", DualCameraMeasurement, hardware_trigger=True
        )
        self.dual_cameras: DualCameraMeasurement

        self.setattr_param_rebind(
            "exposure",
            self.dual_cameras,
            "exposure_horiz",
            description="Camera exposures",
        )
        self.exposure: FloatParamHandle

        # TODO: This rebinding appears not to work
        self.dual_cameras.bind_param("exposure_vert", self.exposure)

        self.setattr_param(
            "expansion_time",
            FloatParam,
            description="Expansion time of MOT",
            default=0.0,
            unit="us",
        )
        self.expansion_time: FloatParamHandle

        self.setattr_fragment("fluorescence_pulse", ImagingFluorescencePulse)
        self.fluorescence_pulse: ImagingFluorescencePulse

        self.setattr_param(
            "use_fluorescence_pulse",
            BoolParam,
            description="Use fluorescence pulse",
            default=True,
        )
        self.use_fluorescence_pulse: BoolParamHandle

        super().build_fragment()

    def host_setup(self):
        self.kernel_invariants = getattr(self, "kernel_invariants", set())
        self.kernel_invariants.add("use_fluorescence_pulse")
        return super().host_setup()  #

        # @kernel
        # def _take_data(self, loading_time):
        #     delay(loading_time)
        #     t = now_mu()
        #     self.mot_controller.turn_off_3d_and_2d_beams()
        #     at_mu(t)
        #     delay(self.expansion_time.get())

        #     with parallel:
        #         self.dual_cameras.trigger()
        #         if self.use_fluorescence_pulse.get():
        #             self.fluorescence_pulse.do_imaging_pulse()
        #         else:
        #             delay(self.exposure.get())

        #     self.core.wait_until_mu(now_mu())

        #     self.dual_cameras.save_data()

    @kernel
    def _take_data(self, loading_time):
        delay(loading_time)

        self.dual_cameras.trigger()

        self.core.wait_until_mu(now_mu())

        self.dual_cameras.save_data()


MeasureBlueMOTWithCamera = make_fragment_scan_exp(MeasureBlueMOTWithCameraFrag)
MeasureBlueMOTWithExpansion = make_fragment_scan_exp(MeasureBlueMOTWithExpansionFrag)
MeasureBlueMOTBGCorrected = make_fragment_scan_exp(MeasureBlueMOTBGCorrectedFrag)
