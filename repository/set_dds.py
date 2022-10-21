# import logging
# import re

# from artiq.coredevice.ad9912 import AD9912
# from artiq.coredevice.core import Core
# from artiq.experiment import BooleanValue
# from artiq.experiment import delay
# from artiq.experiment import delay_mu
# from artiq.experiment import EnumerationValue
# from artiq.experiment import EnvExperiment
# from artiq.experiment import kernel
# from artiq.experiment import NumberValue
# from artiq.master.scheduler import Scheduler


# class SetDDS(EnvExperiment):
#     """Set a DDS channel"""

#     def build(self):
#         self.setattr_device("core")

#         self.setattr_argument(
#             "frequency",
#             NumberValue(default=20e6, unit="MHz", step=0.1e6, ndecimals=1, min=0),
#         )
#         self.setattr_argument(
#             "attenuation",
#             NumberValue(default=0, unit="dB", step=0.1, ndecimals=1, min=0),
#         )
#         self.setattr_argument(
#             "switch_status",
#             BooleanValue(default=True),
#         )

#         urukuls = [
#             k for k in self.get_device_db().keys() if re.match(r"urukul\d_ch\d", k)
#         ]

#         self.setattr_argument("dds_id", EnumerationValue(urukuls))

#         self.dds = self.get_device(self.dds_id)

#     @kernel
#     def run(self):
#         self.core.reset()

#         dds = self.dds  # type: AD9912

#         dds.init()
#         dds.set(self.frequency, 0.0)
#         dds.set_att(self.attenuation)
#         dds.sw.set_o(self.switch_status)


# class ToggleDDS(EnvExperiment):
#     """Toggle a DDS channel"""

#     def build(self):
#         self.setattr_device("core")
#         self.core: Core
#         self.setattr_device("scheduler")
#         self.scheduler: Scheduler

#         self.setattr_argument(
#             "frequency",
#             NumberValue(default=20e6, unit="MHz", step=0.1e6, ndecimals=1, min=0),
#         )
#         self.setattr_argument(
#             "attenuation",
#             NumberValue(default=0, unit="dB", step=0.1, ndecimals=1, min=0),
#         )
#         self.setattr_argument(
#             "toggle_rate",
#             NumberValue(default=1, unit="Hz", step=1, ndecimals=0, min=0),
#         )

#         urukuls = [
#             k for k in self.get_device_db().keys() if re.match(r"urukul\d_ch\d", k)
#         ]

#         self.setattr_argument("dds_id", EnumerationValue(urukuls))

#         self.dds = self.get_device(self.dds_id)
#         self.dds: AD9912

#     @kernel
#     def run(self):
#         dds = self.dds
#         period = 1.0 / self.toggle_rate
#         delay_time_mu = self.core.seconds_to_mu(period / 2)
#         num_cycles_before_scheduler_check = int(1.0 / period)

#         logging.info("period = %s", period)
#         logging.info("delay_time_mu = %s", delay_time_mu)
#         logging.info(
#             "num_cycles_before_scheduler_check = %s", num_cycles_before_scheduler_check
#         )

#         self.core.reset()

#         dds.init()
#         dds.set(self.frequency, 0.0)
#         dds.set_att(self.attenuation)

#         while True:
#             cycles = 0
#             self.core.break_realtime()
#             while cycles < num_cycles_before_scheduler_check:
#                 dds.sw.on()
#                 delay_mu(delay_time_mu)
#                 dds.sw.off()
#                 delay_mu(delay_time_mu)
#                 cycles += 1

#             # Quit here if requested by the scheduler
#             logging.info("Checking for pause...")
#             if self.scheduler.check_pause():
#                 return


# class PulseDDS(EnvExperiment):
#     """Pulse the frequency of a DDS"""

#     def build(self):
#         self.setattr_device("core")
#         self.core: Core
#         self.setattr_device("scheduler")
#         self.scheduler: Scheduler

#         self.setattr_argument(
#             "frequency",
#             NumberValue(default=20e6, unit="MHz", step=0.1e6, ndecimals=1, min=0),
#         )
#         self.setattr_argument(
#             "attenuation",
#             NumberValue(default=0, unit="dB", step=0.1, ndecimals=1, min=0),
#         )
#         self.setattr_argument(
#             "pulse_rate",
#             NumberValue(default=1, unit="Hz", step=1, ndecimals=2, min=0),
#         )
#         self.setattr_argument(
#             "pulse_range",
#             NumberValue(default=3, unit="MHz", step=1, ndecimals=0, min=0),
#         )

#         urukuls = [
#             k for k in self.get_device_db().keys() if re.match(r"urukul\d_ch\d", k)
#         ]

#         self.setattr_argument("dds_id", EnumerationValue(urukuls))

#         self.dds = self.get_device(self.dds_id)
#         self.dds: AD9912

#     @kernel
#     def run(self):
#         dds = self.dds

#         update_period = 1e-3  # keep things chilled
#         half_pulse_period = 1.0 / self.pulse_rate / 2
#         n_update_periods = 2 * int(half_pulse_period / update_period)

#         # make a loopup table of frequencies over all n_update_periods
#         frequencies = [0.0] * n_update_periods

#         for i in range(n_update_periods // 2):
#             frequencies[i] = self.frequency + self.pulse_range * (
#                 4 * i / (n_update_periods) - 1
#             )
#         for i in range(n_update_periods // 2, n_update_periods):
#             frequencies[i] = self.frequency + self.pulse_range * (
#                 3 - 4 * i / n_update_periods
#             )

#         logging.info("update_period = %s", update_period)
#         logging.info("half_pulse_period = %s", half_pulse_period)
#         logging.info("n_update_periods = %s", n_update_periods)

#         self.core.reset()

#         dds.init()
#         dds.set(self.frequency, 0.0)
#         dds.set_att(self.attenuation)
#         dds.sw.on()

#         while True:
#             self.core.break_realtime()

#             for i in range(n_update_periods):
#                 self.dds.set(frequencies[i], 0.0)
#                 delay(update_period)

#             # Quit here if requested by the scheduler
#             logging.info("Checking for pause...")
#             if self.scheduler.check_pause():
#                 return
