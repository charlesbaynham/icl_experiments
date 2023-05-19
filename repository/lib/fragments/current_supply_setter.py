# import logging
# from typing import List
# from artiq.coredevice.core import Core
# from artiq.coredevice.ttl import TTLOut
# from artiq.experiment import kernel
# from ndscan.experiment import Fragment
# from artiq.coredevice.zotino import Zotino
# import repository.lib.constants as constants
# logger = logging.getLogger(__name__)
# class SetAnalogCurrentSupply(Fragment):
#     """
#     Set a current supply that's controlled by an analog voltage
#     """
#     def build_fragment(self, ):
#         self.setattr_device("core")
#         self.core: Core
#         self.
#    @kernel
#     def set_current(self, current):
#         """
#         Set a current in amps.
#         This method does not advance the timeline.
#         """
#         self.
