# import logging
# import logging
# import time

# from artiq.master.scheduler import Scheduler
# from ndscan.experiment import Fragment
# from wand.server import ControlInterface as WANDControlInterface
# from wand.tools import WLMMeasurementStatus
# from artiq.coredevice.ad9910 import AD9910
# from artiq.coredevice.core import Core
# from artiq.language import at_mu
# from artiq.language import delay
# from artiq.language import delay_mu
# from artiq.language import kernel
# from artiq.language import now_mu
# from ndscan.experiment import Fragment
# from ndscan.experiment.parameters import FloatParam
# from ndscan.experiment.parameters import FloatParamHandle
# from numpy import int64
# from pyaion.fragments.default_beam_setter import SetBeamsToDefaults
# from pyaion.fragments.default_beam_setter import make_set_beams_to_default
# from pyaion.fragments.suservo import LibSetSUServoStatic
# from pyaion.models import SUServoedBeam
# from pyaion.models import UrukuledBeam

# from repository.lib import constants
# from repository.lib.experiment_templates.dipole_trap_experiment import (
#     DipoleTrapWithExperiment,
# )
# from repository.lib.experiment_templates.red_mot_experiment import RedMOTWithExperiment
# from repository.lib.fragments

# logger = logging.getLogger(__name__)


# class MonitorAndRelock689and698Mixin(RedMOTWithExperiment):
#     """
#     Mixin to monitor the 689 and 698 cavity locks and relock them if required

#     Kernel hooks used (multiple mixins cannot use the same hooks):

#     * None
#     """

#     def build_fragment(self):
#         super().build_fragment()

#         self.setattr_fragment
