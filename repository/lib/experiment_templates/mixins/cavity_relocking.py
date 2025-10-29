import logging

from artiq.language import kernel
from ndscan.experiment import Fragment
from ndscan.experiment.parameters import BoolParam
from ndscan.experiment.parameters import BoolParamHandle

from repository.lib.experiment_templates.red_mot_experiment import RedMOTWithExperiment
from repository.lib.fragments.relock_689_and_698 import Relock689Frag
from repository.lib.fragments.relock_689_and_698 import Relock698Frag

logger = logging.getLogger(__name__)


class MonitorAndRelock689and698Mixin(RedMOTWithExperiment):
    """
    Mixin to monitor the 689 and 698 cavity locks and relock them if required

    Kernel hooks used (multiple mixins cannot use the same hooks):

    * None
    """

    def build_fragment(self):
        super().build_fragment()

        class MonitorLocksInDeviceSetup(Fragment):
            def build_fragment(self):
                self.setattr_device("core")

                self.setattr_fragment("relock_689_frag", Relock689Frag)
                self.relock_689_frag: Relock689Frag

                self.setattr_fragment("relock_698_frag", Relock698Frag)
                self.relock_698_frag: Relock698Frag

                self.setattr_param(
                    "relock_689_enabled",
                    BoolParam,
                    default=True,
                    description="Enable 689 ECDL automatic relocking",
                )
                self.relock_689_enabled: BoolParamHandle

                self.setattr_param(
                    "relock_698_enabled",
                    BoolParam,
                    default=True,
                    description="Enable 698 ECDL automatic relocking",
                )
                self.relock_698_enabled: BoolParamHandle

            @kernel
            def device_setup(self):
                self.device_setup_subfragments()

                if (
                    self.relock_689_enabled.get()
                    and not self.relock_689_frag.is_cavity_locked(accept_old=True)
                ):
                    logger.warning("689 cavity unlocked, attempting relock")
                    try:
                        self.relock_689_frag.relock()
                    except RuntimeError:
                        logger.error("Failed to relock 689 cavity")

                if (
                    self.relock_698_enabled.get()
                    and not self.relock_698_frag.is_cavity_locked(accept_old=True)
                ):
                    logger.warning("698 cavity unlocked, attempting relock")
                    try:
                        self.relock_698_frag.relock()
                    except RuntimeError:
                        logger.error("Failed to relock 698 cavity")

        self.setattr_fragment(
            "monitor_locks_in_device_setup", MonitorLocksInDeviceSetup
        )
        self.monitor_locks_in_device_setup: MonitorLocksInDeviceSetup
