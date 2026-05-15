import logging

from artiq.coredevice.core import Core
from artiq.coredevice.ttl import TTLInOut
from artiq.language import at_mu
from artiq.language import kernel
from ndscan.experiment import Fragment
from ndscan.experiment.parameters import BoolParam
from ndscan.experiment.parameters import BoolParamHandle
from ndscan.experiment.parameters import FloatParam
from ndscan.experiment.parameters import FloatParamHandle

logger = logging.getLogger(__name__)


class ExternalTriggerFrag(Fragment):
    """
    Trigger the experiment based on a TTL that is triggered by the mains
    """

    def build_fragment(self, ttl_name: str, auto_wait: bool) -> None:
        self.setattr_device("core")
        self.core: Core

        # Get the TTL device for the external trigger
        self.ttl: TTLInOut = self.get_device(ttl_name)

        self.setattr_param(
            "enabled",
            BoolParam,
            "Enable or disable external triggering",
            default=True,
        )
        self.enabled: BoolParamHandle

        self.setattr_param(
            "trigger_offset",
            FloatParam,
            "Delay after the external trigger edge before continuing the experiment",
            default=0.0,
            unit="ms",
        )
        self.trigger_offset: FloatParamHandle

        self.auto_wait = auto_wait

        self.kernel_invariants = getattr(self, "kernel_invariants", set())
        self.kernel_invariants.add("ttl")
        self.kernel_invariants.add("auto_wait")

        self.first_run = False

    @kernel
    def device_setup(self) -> None:
        if self.first_run:
            self.first_run = False

            # Set the TTL to an input
            self.core.break_realtime()
            self.ttl.input()

        if self.auto_wait and self.enabled.get():
            self.wait_for_trigger()

        self.device_setup_subfragments()

    @kernel
    def wait_for_trigger(self) -> None:
        """
        Wait for the next external trigger edge, then apply the configured offset.

        The timeline cursor is advanced to the trigger timestamp plus the offset,
        rounded forward by trigger periods if necessary to ensure the target
        lies in the future.
        """
        if self.enabled.get():
            timeout_mu = self.core.seconds_to_mu(0.2)
            gate_end = self.ttl.gate_rising_mu(timeout_mu)
            offset_mu = self.core.seconds_to_mu(self.trigger_offset.get())

            # Commence waiting for the trigger
            t_mu = self.ttl.timestamp_mu(gate_end)
            if t_mu < 0:
                logger.error("No external trigger detected within 0.2s timeout")
                return

            # Jump the cursor to the target time
            target_mu = t_mu + offset_mu
            at_mu(target_mu)
