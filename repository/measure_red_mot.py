import logging

from artiq.experiment import delay
from artiq.experiment import kernel
from artiq.experiment import now_mu
from artiq.experiment import parallel
from ndscan.experiment.entry_point import make_fragment_scan_exp
from ndscan.experiment.parameters import FloatParam
from ndscan.experiment.parameters import FloatParamHandle


logger = logging.getLogger(__name__)


# FIXME
# # Ensure that both camera are on for the same length of time as the blue
# # fluorescence is pulsed
# self.setattr_param_rebind(
#     "camera_exposure",
#     self.camera_interface,
#     "exposure_horiz",
#     default=constants.DEFAULT_CAMERA_EXPOSURE_TIME,
#     description="Camera exposure time",
#     unit="us",
# )
# self.camera_interface.bind_param(
#     "exposure_vert",
#     self.camera_exposure,
# )
# self.camera_exposure: FloatParamHandle

# self.setattr_param(
#     "fluorescence_pulse_length",
#     FloatParam,
#     "Length of fluorescence pulse",
#     default=constants.DEFAULT_CAMERA_EXPOSURE_TIME,
#     min=0.0,
#     unit="us",
# )
# self.fluorescence_pulse_length: FloatParamHandle


class MeasureBBRedMOTFrag(_BroadbandBase):
    @kernel
    def run_once(self):
        self.prepare_and_load_blue_mot()

        self.start_red_broadband()

        # Note that red_broadband_time may be negative if we're imaging the blue MOT
        delay(self.red_broadband_time.get())

        with parallel:
            self.red_mot_controller.turn_off_mot_beams()
            self.pulse_blue_and_image()

        # Turn the fields back to defaults so eddy currents are gone by the next shot
        self.blue_mot_controller.enable_mot_fields()

        # End of RTIO sequencing. Now we are in real-time.

        # Save the photos
        self.core.wait_until_mu(now_mu())
        self.camera_interface.save_data()


class MeasureBBRedMOTExpansionFrag(_BroadbandBase):
    def build_fragment(self):
        super().build_fragment()

        self.setattr_param(
            "red_expansion_time",
            FloatParam,
            "Expansion time before imaging MOT",
            default=100e-6,
            min=0.0,
            unit="us",
        )
        self.red_expansion_time: FloatParamHandle

    @kernel
    def run_once(self):
        self.prepare_and_load_blue_mot()

        self.start_red_broadband()

        # Unlike for MeasureRedMOT, here we require that red_broadband_time be positive
        delay(self.red_broadband_time.get())

        self.red_mot_controller.turn_off_mot_beams()

        delay(self.red_expansion_time.get())

        self.pulse_blue_and_image()

        # Turn the fields back to defaults so eddy currents are gone by the next shot
        self.blue_mot_controller.enable_mot_fields()

        # End of RTIO sequencing. Now we are in real-time.

        # Save the photos
        self.core.wait_until_mu(now_mu())
        self.camera_interface.save_data()


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
MeasureBBRedMOTExpansion = make_fragment_scan_exp(MeasureBBRedMOTExpansionFrag)
MeasureNarrowbandRedMOT = make_fragment_scan_exp(NarrowbandRedMOTFrag)
