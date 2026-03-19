from artiq.language import delay_mu
from artiq.language import kernel
from numpy import int64

from repository.lib.experiment_templates.mixins.clock_shelving import (
    ClockShelvingAndClearoutBase,
)


class ClockShelvingAndClearoutRedMOTMixin(ClockShelvingAndClearoutBase):
    """
    Uses a clock pulse to state-prepare atoms, then blast away the ground state before spectroscopy

    Kernel hooks used (multiple mixins cannot use the same hooks):

    * :meth:`~before_start_hook`
    * :meth:`~post_narrowband_hook`
    * :meth:`~post_sequence_cleanup_hook`
    """

    @kernel
    def post_narrowband_hook(self):
        self.post_narrowband_hook_default()
        delay_mu(int64(self.core.ref_multiplier))
        self.clock_shelving()
