import logging

from artiq.coredevice.core import Core
from artiq.experiment import delay
from artiq.experiment import kernel
from artiq.experiment import now_mu
from artiq.experiment import parallel
from ndscan.experiment import ExpFragment
from ndscan.experiment.entry_point import make_fragment_scan_exp
from ndscan.experiment.parameters import FloatParam
from ndscan.experiment.parameters import FloatParamHandle

from repository.lib import constants
from repository.lib.fragments.blue_3d_mot import Blue3DMOTFrag
from repository.lib.fragments.dual_camera_measurer import DualCameraMeasurement
from repository.lib.fragments.fluorescence_pulse import FluorescencePulse
from repository.lib.fragments.red_mot import NarrowbandRedMOTFrag

logger = logging.getLogger(__name__)


class MeasureBBRedMOTFrag(ExpFragment):
    def build_fragment(self) -> None:
        self.setattr_device("core")
        self.core: Core

        # %% Fragments

        self.setattr_fragment("blue_3d_mot", Blue3DMOTFrag)
        self.blue_3d_mot: Blue3DMOTFrag

        self.setattr_fragment("red_mot", NarrowbandRedMOTFrag)
        self.red_mot: NarrowbandRedMOTFrag

        self.setattr_fragment("camera_interface", DualCameraMeasurement)
        self.camera_interface: DualCameraMeasurement

        self.setattr_fragment("fluorescence_pulse", FluorescencePulse)
        self.fluorescence_pulse: FluorescencePulse

        # %% Params

        # Expansion time - can be negative
        self.setattr_param(
            "expansion_time",
            FloatParam,
            "Time to expand MOT for before imaging",
            default=5e-3,
            unit="us",
        )
        self.expansion_time: FloatParamHandle

        # %% Rebound params

        self.setattr_param_rebind(
            "exposure_horiz",
            self.camera_interface,
            "exposure_horiz",
            default=constants.DEFAULT_CAMERA_EXPOSURE_TIME,
            description="Horizontal camera exposure time",
            unit="us",
        )
        self.setattr_param_rebind(
            "exposure_vert",
            self.camera_interface,
            "exposure_vert",
            default=constants.DEFAULT_CAMERA_EXPOSURE_TIME,
            description="Vertical camera exposure time",
            unit="us",
        )
        self.exposure_horiz: FloatParamHandle
        self.exposure_vert: FloatParamHandle

        self.setattr_param_rebind(
            "injection_aom_static_detuning",
            self.red_mot,
        )

    @kernel
    def run_once(self):
        self.blue_3d_mot.load_mot(clearout=True)

        self.blue_3d_mot.turn_off_3d_beams()
        self.red_mot.load_narrowband_mot_from_blue_mot()

        self.red_mot.red_beam_controller.turn_off_mot_beams()

        delay(self.expansion_time.get())

        with parallel:
            self.fluorescence_pulse.do_imaging_pulse()
            self.camera_interface.trigger()

        # Turn the fields back to defaults so eddy currents are gone by the next shot
        delay(1e-3)
        self.blue_3d_mot.enable_mot_fields()

        # End of RTIO sequencing. Now we are in real-time.

        # Save the photos
        self.core.wait_until_mu(now_mu())
        self.camera_interface.save_data()


# class MeasureBBRedMOTExpansionFrag(_BroadbandBase):
#     def build_fragment(self):
#         super().build_fragment()

#         self.setattr_param(
#             "red_expansion_time",
#             FloatParam,
#             "Expansion time before imaging MOT",
#             default=100e-6,
#             min=0.0,
#             unit="us",
#         )
#         self.red_expansion_time: FloatParamHandle

#     @kernel
#     def run_once(self):
#         self.prepare_and_load_blue_mot()

#         self.start_red_broadband()

#         # Unlike for MeasureRedMOT, here we require that red_broadband_time be positive
#         delay(self.red_broadband_time.get())

#         self.red_mot_controller.turn_off_mot_beams()

#         delay(self.red_expansion_time.get())

#         self.pulse_blue_and_image()

#         # Turn the fields back to defaults so eddy currents are gone by the next shot
#         self.blue_mot_controller.enable_mot_fields()

#         # End of RTIO sequencing. Now we are in real-time.

#         # Save the photos
#         self.core.wait_until_mu(now_mu())
#         self.camera_interface.save_data()


## % Commented out spectroscopy experiment - unusable until we have more red power
# class MeasureRedMOTSpectroscopy(_MeasureRedMOTBase):
#     def build_fragment(self):
#         super().build_fragment()

#         self.setattr_param(
#             "red_expansion_time",
#             FloatParam,
#             "Expansion time before pulsing 689",
#             default=10e-3,
#             unit="ms",
#         )
#         self.red_expansion_time: FloatParamHandle

#         self.setattr_param(
#             "spectroscopy_pulse_time",
#             FloatParam,
#             "Length of spectroscopy pulse",
#             default=50e-6,
#             unit="us",
#         )
#         self.spectroscopy_pulse_time: FloatParamHandle

#         self.setattr_param(
#             "spectroscopy_pulse_aom_frequency",
#             FloatParam,
#             "Frequency of AOM during spectroscopy pulse",
#             default=340e6,
#             unit="MHz",
#         )
#         self.spectroscopy_pulse_aom_frequency: FloatParamHandle

#     @kernel
#     def run_once(self):
#         if self.red_broadband_time.get() < 0:
#             raise RuntimeError("red_broadband_time must be greater than zero")

#         self.prepare_and_load_blue_mot()

#         self.start_red_loading()

#         # Unlike for MeasureRedMOT, here we require that red_broadband_time be positive
#         delay(self.red_broadband_time.get())

#         with parallel:
#             self.chamber_2_field_setter.set_mot_gradient(0.0)
#             self.red_mot_controller.turn_off_mot_beams(ignore_shutters=True)
#             self.red_mot_controller.stop_ramping_red(
#                 freq=self.spectroscopy_pulse_aom_frequency.get()
#             )

#         delay(self.red_expansion_time.get())

#         self.red_mot_controller.turn_on_mot_beams(ignore_shutters=True)
#         delay(self.spectroscopy_pulse_time.get())
#         self.red_mot_controller.turn_off_mot_beams()

#         with parallel:
#             self.camera_interface.trigger()
#             self.pulse_blue_for_image()

#         # Turn the fields back to defaults so eddy currents are gone by the next shot
#         self.blue_mot_controller.enable_mot_fields()

#         # End of RTIO sequencing. Now we are in real-time.

#         # Save the photos
#         self.core.wait_until_mu(now_mu())
#         self.camera_interface.save_data()


MeasureBBRedMOT = make_fragment_scan_exp(MeasureBBRedMOTFrag)
# MeasureBBRedMOTExpansion = make_fragment_scan_exp(MeasureBBRedMOTExpansionFrag)
# MeasureNarrowbandRedMOT = make_fragment_scan_exp(NarrowbandRedMOTFrag)
