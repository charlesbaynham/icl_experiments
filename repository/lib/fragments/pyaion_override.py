from pyaion.fragments.beam_setter import ControlBeamsWithoutCoolingAOM


# import logging
# from typing import List

# from artiq.coredevice.core import Core
# from artiq.coredevice.suservo import Channel as SUServoChannel
# from artiq.coredevice.ttl import TTLOut
# from artiq.experiment import at_mu
# from artiq.experiment import delay
# from artiq.experiment import kernel
# from artiq.experiment import now_mu
# from artiq.experiment import TInt64
# from ndscan.experiment import Fragment
# from pyaion.models import SUServoedBeam

# DELAY_BETWEEN_RTIO_EVENTS = 4e-9

# logger = logging.getLogger(__name__)


# class ControlBeamsWithoutCoolingAOM(Fragment):
#     """
#     Methods to turn on/off a list of beams using a SUServoed AOM for sharp edges
#     and a shutter to fully block it

#     The AOMs will be left on as much as possible even while the beams are off
#     (but blocked with the shutter) to avoid pointing instability from thermal
#     effects.

#     Note that when groups of beams are intended to be turned on together, you
#     should use a single instance of this fragment to control all of them rather
#     than initialising one for each beam. That's because this fragment skips
#     forwards and backwards in time and will therefore wantonly consume RTIO
#     lanes unless you let it reduce this behaviour by knowing in advance which
#     shutters need to be opened.

#     Note that the beam turn-on/off events will not quite be simultaneous, but
#     will actually be separated by 4ns. This is so that only one RTIO lane is
#     consumed, avoiding collisions. If this is unacceptable for your application,
#     you will need to manage the lane usage manually.

#     Example usage
#     -------------

#     This example just turns on and off one beam, but you could (and should) pass
#     several. This is a :class:`~ndscan.experiment.fragment.Fragment` and so needs to be called from another
#     fragment.::

#         from artiq.experiment import kernel
#         from ndscan.experiment import Fragment
#         from pyaion.fragments.beam_setter import ControlBeamsWithoutCoolingAOM
#         from pyaion.models import SUServoedBeam

#         my_beam = SUServoedBeam(
#             name="my_blue_beam_for_physics_stuff",
#             frequency="150e6",
#             attenuation=20,
#             suservo_device="suservo_aom_singlepass_461_2DMOT_A",
#             shutter_device="TTL_shutter_461_2DMOT_A",
#             shutter_delay=20e-3,
#         )


#         class MyBeamTurnerOnnerer(Fragment):
#             def build_fragment(self):
#                 self.setattr_fragment(
#                     "my_beam_setter", ControlBeamsWithoutCoolingAOM,
#                     beam_infos=[my_beam],
#                 )
#                 self.my_beam_setter: ControlBeamsWithoutCoolingAOM

#             @kernel def turn_on_the_beam(self):
#                 self.core.break_realtime()
#                 self.my_beam_setter.turn_beams_on()

#             @kernel def turn_off_the_beam(self):
#                 self.core.break_realtime()
#                 self.my_beam_setter.turn_beams_off()
#     """

#     def build_fragment(self, beam_infos: List[SUServoedBeam]):
#         logger.debug("Building with %s", beam_infos)
#         self.beam_infos = beam_infos

#         self.setattr_device("core")
#         self.core: Core

#         self.beam_suservos: List[SUServoChannel] = []
#         self.beam_shutters: List[TTLOut] = []
#         self.beam_delays: List[float] = []

#         for beam_info in beam_infos:
#             if beam_info.shutter_device is None:
#                 raise ValueError(
#                     "Beam [{:s}] has no shutter configured".format(beam_info.name)
#                 )

#             self.beam_suservos.append(self.get_device(beam_info.suservo_device))
#             self.beam_shutters.append(self.get_device(beam_info.shutter_device))
#             self.beam_delays.append(beam_info.shutter_delay)

#         # Sort beams by order of delay - smallest delay first
#         tupled = list(zip(self.beam_suservos, self.beam_shutters, self.beam_delays))

#         logger.debug("tupled = %s", tupled)
#         logger.debug("tupled[0] = %s", tupled[0])

#         sorted_tupled = sorted(tupled, key=lambda v: v[2])
#         self.beam_suservos, self.beam_shutters, self.beam_delays = zip(*sorted_tupled)

#         # Convert them back to lists - python has turned them into tuples
#         self.beam_suservos = list(self.beam_suservos)
#         self.beam_shutters = list(self.beam_shutters)
#         self.beam_delays = list(self.beam_delays)

#         logger.debug("sorted_tupled = %s", sorted_tupled)

#     @kernel
#     def turn_beams_on(self) -> TInt64:
#         """
#         Turn on the beams using the AOM and shutter

#         This method will use the AOM to turn on the beam at the cursor, having
#         first disabled the AOM and opened the shutter to prevent the AOM from
#         cooling down too much.

#         Start with the shutters with the longest delay to avoid switching
#         backwards and forwards in time.

#         This method does not advance the cursor. However, it will reverse time
#         to write shutter opening into the past. You should therefore make sure
#         that there is at least "shutter_delay_time" slack, ideally with no
#         queued RTIO events to prevent using a new RTIO lane.

#         Returns the RTIO timestamp furthest into the future
#         """

#         start_mu = now_mu()

#         for i in range(len(self.beam_delays) - 1, -1, -1):
#             suservo = self.beam_suservos[i]
#             shutter = self.beam_shutters[i]
#             delay_by = self.beam_delays[i]

#             delay(-delay_by)

#             suservo.set(en_out=0, en_iir=0)
#             delay(DELAY_BETWEEN_RTIO_EVENTS)
#             shutter.on()
#             delay(DELAY_BETWEEN_RTIO_EVENTS)

#             delay(delay_by)

#         for i in range(len(self.beam_delays) - 1, -1, -1):
#             suservo = self.beam_suservos[i]

#             suservo.set(en_out=1, en_iir=0)

#             delay(DELAY_BETWEEN_RTIO_EVENTS)

#         # Cancel out the accumulated tiny delays so that we do not affect the
#         # cursor position
#         t_latest = now_mu()
#         at_mu(start_mu)

#         return t_latest

#     @kernel
#     def turn_beams_off(self) -> TInt64:
#         """
#         Turn off the beams using the AOM and shutter

#         This method will turn off the beam at the cursor and then close the
#         shutter and turn the AOM back on to stop it cooling down.

#         This method will not advance the cursor BUT will write shutter closing
#         events into the future by "shutter_delay_time" seconds.

#         Returns the RTIO timestamp furthest into the future
#         """

#         start_mu = now_mu()

#         delay_by = 0.0

#         # AOMs off
#         for i in range(len(self.beam_delays)):
#             suservo = self.beam_suservos[i]

#             suservo.set(en_out=0, en_iir=0)
#             delay(DELAY_BETWEEN_RTIO_EVENTS)

#         # Shutters closed
#         for i in range(len(self.beam_delays)):
#             shutter = self.beam_shutters[i]

#             shutter.off()
#             delay(DELAY_BETWEEN_RTIO_EVENTS)

#         # AOMs back on
#         for i in range(len(self.beam_delays)):
#             suservo = self.beam_suservos[i]
#             delay_by = self.beam_delays[i]

#             delay(delay_by)

#             suservo.set(en_out=1, en_iir=0)
#             delay(DELAY_BETWEEN_RTIO_EVENTS)

#             delay(-delay_by)

#         t_latest = now_mu() + self.core.seconds_to_mu(delay_by)

#         # Cancel out the accumulated tiny delays so that we do not affect the
#         # cursor position
#         at_mu(start_mu)

#         return t_latest
