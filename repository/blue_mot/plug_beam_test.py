# from artiq.coredevice.core import Core
# from artiq.experiment import kernel
# from artiq.experiment import now_mu
# from ndscan.experiment import ExpFragment
# from ndscan.experiment import FloatChannel
# from ndscan.experiment import ResultChannel
# from ndscan.experiment import delay
# from ndscan.experiment.entry_point import make_fragment_scan_exp
# from ndscan.experiment.parameters import FloatParam
# from ndscan.experiment.parameters import FloatParamHandle

# from repository.lib.fragments.blue_3d_mot import Blue3DMOTFrag
# from repository.lib.fragments.cameras.dual_camera_measurer import DualCameraMeasurement
# from repository.lib.fragments.pyaion_overrides.default_beam_setter_override import (
#     SetBeamsToDefaults,
# )
# from repository.lib.fragments.read_adc import ReadSUServoADC

# # PlugBeamSetter = make_set_beams_to_default(
# #     suservo_beam_infos=[
# #         constants.SUSERVOED_BEAMS["blue_plug_beam"],
# #     ],
# #     urukul_beam_infos=[],
# #     name="PlugBeamSetter",
# # )


# class ScanPlugBeamParamsFrag(ExpFragment):
#     def build_fragment(self) -> None:
#         self.setattr_device("core")
#         self.core: Core

#         self.setattr_fragment("blue_mot", Blue3DMOTFrag)
#         self.blue_mot: Blue3DMOTFrag

#         self.setattr_fragment(
#             "dual_cameras", DualCameraMeasurement, hardware_trigger=True
#         )
#         self.dual_cameras: DualCameraMeasurement

#         # self.setattr_fragment("plug_beam_default_setter", PlugBeamSetter)
#         # self.plug_beam_default_setter: SetBeamsToDefaults

#         self.setattr_param_rebind("mot_loading_time", self.blue_mot, "loading_time")
#         self.mot_loading_time: FloatParamHandle

#         self.setattr_param(
#             "delay_between_points",
#             FloatParam,
#             "Delay between measurements",
#             default=20e-3,
#             min=0,
#             unit="s",
#         )
#         self.delay_between_points: FloatParamHandle

#         self.setattr_param_rebind(
#             "plug_beam_setpoint",
#             self.plug_beam_default_setter,
#             "setpoint_blue_plug_beam",
#             description="Setpoint",
#         )
#         self.plug_beam_setpoint: FloatParamHandle

#         self.setattr_param_rebind(
#             "plug_beam_frequency",
#             self.plug_beam_default_setter,
#             "frequency_blue_plug_beam",
#             description="Frequency",
#         )
#         self.plug_beam_frequency: FloatParamHandle

#         self.setattr_result("photodiode_voltage", FloatChannel)
#         self.photodiode_voltage: ResultChannel

#         self.setattr_fragment(
#             "adc_reader",
#             ReadSUServoADC,
#             self.get_device("suservo_aom_doublepass_461_plug"),
#         )
#         self.adc_reader: ReadSUServoADC

#     @kernel
#     def run_once(self) -> None:
#         # Turn on the plug beam and set its amplitude, setpoint and frequency
#         self.plug_beam_default_setter.turn_on_all()

#         self.blue_mot.load_mot()  # This turns on MOT coils, "clears out" for 100ms, then turns on MOT beams, and waits for loading time

#         delay(500e-3)

#         self.dual_cameras.trigger()

#         self.core.wait_until_mu(now_mu())

#         self.dual_cameras.save_data()

#         self.core.break_realtime()
#         photodiode_voltage = self.adc_reader.read_adc()
#         self.photodiode_voltage.push(photodiode_voltage)
#         self.core.break_realtime()
#         self.blue_mot.turn_off_all_beams()

#         delay(self.delay_between_points.get())


# ScanPlugBeamParams = make_fragment_scan_exp(ScanPlugBeamParamsFrag)
