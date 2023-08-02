import logging

from artiq.coredevice.core import Core
from artiq.experiment import delay
from artiq.experiment import delay_mu
from artiq.experiment import kernel
from artiq.experiment import now_mu
from artiq.experiment import parallel
from ndscan.experiment import ExpFragment
from ndscan.experiment.entry_point import make_fragment_scan_exp
from ndscan.experiment.parameters import FloatParam
from ndscan.experiment.parameters import FloatParamHandle

from repository.lib.fragments.blue_3d_mot import Blue3DMOTFrag
from repository.lib.fragments.dual_camera_measurer import DualCameraMeasurement
from repository.lib.fragments.magnetic_fields import SetMagneticFields
from repository.lib.fragments.red_3d_mot import Red3DMOTFrag

logger = logging.getLogger(__name__)


class _MeasureRedMOTBase(ExpFragment):
    def build_fragment(self):
        self.setattr_device("core")
        self.core: Core

        self.setattr_fragment("blue_mot_controller", Blue3DMOTFrag)
        self.blue_mot_controller: Blue3DMOTFrag

        self.setattr_fragment("red_mot_controller", Red3DMOTFrag)
        self.red_mot_controller: Red3DMOTFrag

        self.setattr_fragment(
            "chamber_2_field_setter",
            SetMagneticFields,
        )
        self.chamber_2_field_setter: SetMagneticFields

        self.setattr_fragment(
            "camera_interface", DualCameraMeasurement, hardware_trigger=True
        )
        self.camera_interface: DualCameraMeasurement

        self.setattr_param(
            "red_broadband_time",
            FloatParam,
            "Time to spend in the broadband red mot",
            default=10e-3,
            unit="ms",
        )
        self.red_broadband_time: FloatParamHandle

        self.setattr_param(
            "red_broadband_gradient_current",
            FloatParam,
            "Current for gradient coils for broadband red MOT stage",
            default=10,
            unit="A",
        )
        self.red_broadband_gradient_current: FloatParamHandle

        # Ensure that both camera are on for the same length of time as the blue
        # fluorescence is pulsed
        self.setattr_param_rebind(
            "camera_exposure",
            self.camera_interface,
            "exposure_horiz",
            default=200e-6,
            description="Camera exposure and fluorescence pulse length",
        )
        self.camera_interface.bind_param(
            "exposure_vert",
            self.camera_exposure,
        )
        self.camera_exposure: FloatParamHandle

    @kernel
    def prepare_and_load_blue_mot(self):
        """
        Advances the timeline to the end of "blue loading time" and leave all
        the blue beams on
        """
        self.core.break_realtime()
        self.blue_mot_controller.init()
        self.red_mot_controller.init()

        # Clear the camera buffer in case we quit a previous sequence midway
        self.camera_interface.clear()

        self.core.break_realtime()

        # Load a blue mot
        self.blue_mot_controller.load_mot(clearout=True)

    @kernel
    def start_red_broadband(self):
        """
        Start sweeping red IJD, turn on the beams and drop the gradient

        Does not advance the timeline
        """

        self.red_mot_controller.turn_on_mot_beams()
        delay_mu(8)
        self.red_mot_controller.start_ramping_red()
        delay_mu(8)
        self.blue_mot_controller.turn_off_3d_and_2d_beams()  # ...but leave repumpers on
        delay_mu(8)
        self.chamber_2_field_setter.set_mot_gradient(
            self.red_broadband_gradient_current.get()
        )

        delay_mu(-3 * 8)

    @kernel
    def pulse_blue_for_image(self):
        # Flash on the blue light
        self.blue_mot_controller.turn_on_3d_beams()
        delay(self.camera_exposure.get())
        self.blue_mot_controller.turn_off_3d_beams()
        delay(self.camera_exposure.get())


class MeasureBBRedMOTFrag(_MeasureRedMOTBase):
    @kernel
    def run_once(self):
        self.prepare_and_load_blue_mot()

        self.start_red_broadband()

        # Note that red_broadband_time may be negative if we're imaging the blue MOT
        delay(self.red_broadband_time.get())

        with parallel:
            self.red_mot_controller.turn_off_mot_beams()
            self.camera_interface.trigger()
            self.pulse_blue_for_image()

        # Turn the fields back to defaults so eddy currents are gone by the next shot
        self.blue_mot_controller.enable_mot_fields()

        # End of RTIO sequencing. Now we are in real-time.

        # Save the photos
        self.core.wait_until_mu(now_mu())
        self.camera_interface.save_data()


class MeasureBBRedMOTExpansion(_MeasureRedMOTBase):
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

        with parallel:
            self.camera_interface.trigger()
            self.pulse_blue_for_image()

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


MeasureBBRedMOTFrag = make_fragment_scan_exp(MeasureBBRedMOTFrag)
MeasureBBRedMOTExpansion = make_fragment_scan_exp(MeasureBBRedMOTExpansion)
