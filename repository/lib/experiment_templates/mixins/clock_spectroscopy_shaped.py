import logging

from artiq.experiment import kernel

from repository.lib.experiment_templates.dipole_trap_experiment import (
    DipoleTrapWithExperiment,
)
from repository.lib.experiment_templates.mixins.clock_spectroscopy import (
    CLOCK_BEAM_INFO,
)
from repository.lib.experiment_templates.mixins.clock_spectroscopy import (
    ClockRabiSpectroscopyBase,
)
from repository.lib.experiment_templates.red_mot_experiment import RedMOTWithExperiment
from repository.lib.fragments.pulse_shaping import BlackmanShapedPulse

logger = logging.getLogger(__name__)


class ShapedRabiSpectroscopy(ClockRabiSpectroscopyBase):
    """
    Sets up the clock beam for clock spectroscopy with a shaped pulse

    Kernel hooks used (multiple mixins cannot use the same hooks):

    * :meth:`~before_start_hook`
    * :meth:`~do_first_pulse`
    * :meth:`~pre_expansion_hook`
    * :meth:`~post_sequence_cleanup_hook`
    """

    def build_fragment(self):
        super().build_fragment()

        self.setattr_fragment(
            "clock_spectroscopy_shaped_pulse",
            BlackmanShapedPulse,
            ad9910_name=CLOCK_BEAM_INFO.urukul_device,
        )
        self.clock_spectroscopy_shaped_pulse: BlackmanShapedPulse

        self.clock_spectroscopy_shaped_pulse.bind_param(
            "pulse_duration", self.spectroscopy_pulse_time
        )

    @kernel
    def fire_clock_spec_pulse(self):
        self.clock_spectroscopy_shaped_pulse.trigger_pulse()

    @kernel
    def pre_expansion_hook(self):
        """
        Pre-expansion hook for the shaped pulse

        Set up the clock beam for RAM mode.
        """
        self.clock_spectroscopy_shaped_pulse.prepare_pulse(
            frequency=CLOCK_BEAM_INFO.frequency
        )

    @kernel
    def post_sequence_cleanup_hook(self):
        self.core.break_realtime()
        self.clock_spectroscopy_shaped_pulse.disable_ram_mode()

        self.post_sequence_cleanup_hook_base()


class ShapedRabiSpectroscopyRedMotMixin(ShapedRabiSpectroscopy, RedMOTWithExperiment):
    """
    Uses a clock pulse for spectroscopy after the red MOT

    Kernel hooks used (multiple mixins cannot use the same hooks):

    * :meth:`~before_start_hook`
    * :meth:`~do_first_pulse`
    * :meth:`~pre_expansion_hook`
    * :meth:`~post_sequence_cleanup_hook`
    """

    @kernel
    def do_experiment_after_red_mot_hook(self):
        self.do_rabi_spectroscopy()


class ShapedRabiSpectroscopyDipoleTrapMixin(
    ShapedRabiSpectroscopy, DipoleTrapWithExperiment
):
    """
    Implements clock Rabi spectroscopy after the dipole trap

    Kernel hooks used (multiple mixins cannot use the same hooks):

    * :meth:`~before_start_hook`
    * :meth:`~do_first_pulse`
    * :meth:`~pre_expansion_hook`
    * :meth:`~post_sequence_cleanup_hook`
    """

    @kernel
    def do_experiment_after_dipole_trap_hook(self):
        self.do_rabi_spectroscopy()
