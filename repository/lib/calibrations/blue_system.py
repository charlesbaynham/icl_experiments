# import logging
# from artiq.coredevice.core import Core
# from artiq.coredevice.suservo import Channel
# from artiq.language import kernel
# from ndscan.experiment import FloatParam
# from ndscan.experiment.entry_point import make_fragment_scan_exp
# from ndscan.experiment.parameters import FloatParamHandle
# from repository.lib.fragments.pyaion_overrides.suservo_override import LibSetSUServoStatic
# from qbutler.calibration import Calibration
# from qbutler.calibration import CalibrationResult
# import repository.lib.constants as constants
# logger = logging.getLogger(__name__)
# def make_static_AOM_calibration(
#     name, description: str, default_frequency, default_attenuation, device_name
# ):
#     class CreatedClass(Calibration):
#         description
#         def build_calibration(self):
#             self.setup_completed = False
#             self.setattr_device("core")
#             self.core: Core
#             self.setattr_param(
#                 "frequency",
#                 FloatParam,
#                 description="Frequency of the AOM",
#                 default=default_frequency,
#                 min=0,
#                 max=400e6,  # from AD9910 specs
#                 unit="MHz",
#                 step=0.1,
#             )
#             self.setattr_param(
#                 "attenuation",
#                 FloatParam,
#                 description="Attenuation on Urukul's variable attenuator",
#                 default=default_attenuation,
#                 min=0,
#                 max=31.5,
#             )
#             self.frequency: FloatParamHandle
#             self.attenuation: FloatParamHandle
#             self.setattr_fragment(
#                 "LibSetSUServoStatic",
#                 LibSetSUServoStatic,
#                 device_name,
#             )
#             self.LibSetSUServoStatic: LibSetSUServoStatic
#         @kernel
#         def run_once(self):
#             # This calibration is always OK - its turns on the AOM in the setup
#             # which is always called directly before this run_once method
#             self.status.push(CalibrationResult.OK)
#         @kernel
#         def device_setup(self):
#             self.device_setup_subfragments()
#             self.core.break_realtime()
#             self.LibSetSUServoStatic.set_suservo(
#                 self.frequency.get(), 1.0, self.attenuation.get()
#             )
#     CreatedClass.__name__ = name
#     return CreatedClass
# BlueInjectionAOM = make_static_AOM_calibration(
#     "BlueInjectionAOM",
#     "Ensure that the double-pass AOM which injects the blue diodes has been set up and turned on",
#     constants.BLUE_INJECTION_AOM_DEFAULT_FREQUENCY,
#     constants.BLUE_INJECTION_AOM_ATTENUATION,
#     "suservo_aom_doublepass_461_injection",
# )
# BlueProbeAOM = make_static_AOM_calibration(
#     "BlueProbeAOM",
#     "Ensure that the single-pass AOM which powers the probes has been set up and turned on",
#     constants.BLUE_PROBE_AOM_DEFAULT_FREQUENCY,
#     constants.BLUE_PROBE_AOM_ATTENUATION,
#     "suservo_aom_singlepass_461_spectroscopy",
# )
# BluePushbeamAOM = make_static_AOM_calibration(
#     "BluePushbeamAOM",
#     "Ensure that the push-beam AOM has been set up and turned on",
#     constants.BLUE_PUSHBEAM_AOM_DEFAULT_FREQUENCY,
#     constants.BLUE_PUSHBEAM_AOM_ATTENUATION,
#     "suservo_aom_singlepass_461_pushbeam",
# )
# Blue2DMOTA_AOM = make_static_AOM_calibration(
#     "Blue2DMOTA_AOM",
#     "Ensure that the 2D MOT A beam AOM has been set up and turned on",
#     constants.BLUE_2DMOT_A_AOM_DEFAULT_FREQUENCY,
#     constants.BLUE_2DMOT_A_AOM_ATTENUATION,
#     "suservo_aom_singlepass_461_2dmot_a",
# )
# Blue2DMOTB_AOM = make_static_AOM_calibration(
#     "Blue2DMOTB_AOM",
#     "Ensure that the 2D MOT B beam AOM has been set up and turned on",
#     constants.BLUE_2DMOT_B_AOM_DEFAULT_FREQUENCY,
#     constants.BLUE_2DMOT_B_AOM_ATTENUATION,
#     "suservo_aom_singlepass_461_2dmot_b",
# )
# class BlueSystemStatic(Calibration):
#     """
#     Turn the blue system fully on
#     """
#     def build_calibration(self):
#         self.add_dependency(BlueInjectionAOM)
#         self.add_dependency(BlueProbeAOM)
#         self.add_dependency(BluePushbeamAOM)
#         self.add_dependency(Blue2DMOTA_AOM)
#         self.add_dependency(Blue2DMOTB_AOM)
#     @kernel
#     def run_once(self):
#         # This calibration is always OK - it just inherits
#         self.status.push(CalibrationResult.OK)
# ## Make some interfaces
# TurnOnBlueInjectionAOM = make_fragment_scan_exp(BlueInjectionAOM)
# BlueProbeAOM = make_fragment_scan_exp(BlueProbeAOM)
# BlueSystemStatic = make_fragment_scan_exp(BlueSystemStatic)
