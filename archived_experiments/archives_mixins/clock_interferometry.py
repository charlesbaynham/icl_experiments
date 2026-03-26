from artiq.language import kernel

from repository.lib.experiment_templates.mixins.clock_interferometry import (
    ClockInterferometryBase,
)


class ClockInterferometryRedMOTMixin(ClockInterferometryBase):
    """
    Implements clock interferometry after the red MOT

    Kernel hooks used (multiple mixins cannot use the same hooks):

    * :meth:`~before_start_hook`
    * :meth:`~do_experiment_after_red_mot_hook`
    * :meth:`~do_first_pulse`
    """

    @kernel
    def do_experiment_after_red_mot_hook(self):
        self.do_clock_interferometry()
