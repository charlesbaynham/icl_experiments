# import time
# from artiq.experiment import EnumerationValue
# from artiq.experiment import EnvExperiment
# from artiq.experiment import NumberValue
# from artiq.experiment import TerminationRequested
# from toptica.lasersdk.dlcpro.v2_6_0
# from libs.lib_data_writer import DataWriter
# class LogTopticaLaser(EnvExperiment):
#     """
#     LogTopticaLaser
#     Logs the voltage, current, temperature of either Toptica laser (370 or 399).
#     Also logs the cavity transmission of the 370 laser.
#     """
#     def build(self):
#         self.setattr_argument("interval", NumberValue(default=0.3, unit="s"))
#         self.setattr_argument(
#             "laser_name",
#             EnumerationValue(
#                 ["Toptica_370_dlcpro", "Toptica_399_dlcpro"],
#                 default="Toptica_370_dlcpro",
#             ),
#         )
#         self.laser = self.get_device(self.laser_name)
#         self.setattr_device("scheduler")
#         self.set_default_scheduling(pipeline_name=self.laser_name, priority=-10)
#         self.data_writer = DataWriter(self)
#     def prepare(self):
#         """
#         Prepares the relevant plots and selects which one of the lasers we are logging.
#         """
#         super().prepare()
#         self.data_writer.build_plot("laser_voltage", title="Toptica voltage")
#         self.data_writer.build_plot("laser_current", title="Toptica current")
#         self.data_writer.build_plot("laser_temperature", title="Toptica temperature")
#         self.data_writer.build_plot("laser_transmission", title="Toptica transmission")
#         if self.laser_name == "Toptica_370_dlcpro":
#             self.laser_wavelength = "370"
#         elif self.laser_name == "Toptica_399_dlcpro":
#             self.laser_wavelength = "399"
#     def run(self):
#         dlcpro: DLCpro = self.laser.get_dlcpro()
#         the_laser = self.laser.get_laser()
#         self.data_writer.init(sync_core=False)
#         with self.laser:
#             while True:
#                 voltage = the_laser.dl.pc.voltage_act.get()
#                 current = the_laser.dl.cc.current_act.get()
#                 transmission = dlcpro.io.fine_1.value_act.get()
#                 temperature = the_laser.dl.tc.temp_set.get()
#                 t = time.time()
#                 self.data_writer.append_plot("laser_voltage", t, voltage, no_core=True)
#                 self.data_writer.append_plot("laser_current", t, current, no_core=True)
#                 self.data_writer.append_plot(
#                     "laser_temperature", t, temperature, no_core=True
#                 )
#                 self.data_writer.append_plot(
#                     "laser_transmission", t, transmission, no_core=True
#                 )
#                 self.data_writer.write_to_database(
#                     f"toptica_{self.laser_wavelength}_log",
#                     fields={
#                         "voltage": voltage,
#                         "current": current,
#                         "transmission": transmission,
#                         "temperature": temperature,
#                     },
#                 )
#                 time.sleep(self.interval)
#                 try:
#                     self.scheduler.pause()
#                 except TerminationRequested:
#                     return
