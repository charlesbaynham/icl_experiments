import logging

from artiq.language import delay_mu
from artiq.language import kernel
from numpy import int64

from repository.lib.experiment_templates.mixins.clock_shelving import (
    ClockShelvingAndClearoutDipoleTrapMixin,
)
from repository.lib.experiment_templates.mixins.clock_spectroscopy import (
    CLOCK_BEAM_INFO,
)
from repository.lib.experiment_templates.mixins.clock_spectroscopy import (
    ClockRabiSpectroscopyDipoleTrapMixin,
)
from repository.lib.fragments.pulse_shaping import BlackmanShapedPulse

logger = logging.getLogger(__name__)


class ShapedRabiSpectroscopyDipoleTrapMixin(ClockRabiSpectroscopyDipoleTrapMixin):
    """
    Sets up the clock beam for clock spectroscopy with a shaped pulse in a
    dipole trap

    Kernel hooks used (multiple mixins cannot use the same hooks):

    * :meth:`~before_start_hook`
    * :meth:`~do_first_pulse`
    * :meth:`~post_dipole_trap_hook`
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
    def post_dipole_trap_hook(self):
        self.post_dipole_trap_hook_shaped_pulses()
        delay_mu(int64(self.core.ref_multiplier))
        self.post_dipole_trap_hook_default()

    @kernel
    def post_dipole_trap_hook_shaped_pulses(self):
        """
        Before spectroscopy in the dipole trap, set up the clock beam for RAM
        mode
        """
        self.clock_spectroscopy_shaped_pulse.prepare_pulse(
            frequency=CLOCK_BEAM_INFO.frequency
        )

    @kernel
    def post_sequence_cleanup_hook(self):
        self.core.break_realtime()
        self.clock_spectroscopy_shaped_pulse.disable_ram_mode()

        self.post_sequence_cleanup_hook_base()


class ShapedClockShelvingAndClearoutDipoleTrapMixin(
    ClockShelvingAndClearoutDipoleTrapMixin
):

    def build_fragment(self):
        super().build_fragment()

        self.setattr_fragment(
            "clock_shelving_shaped_pulse",
            BlackmanShapedPulse,
            ad9910_name=CLOCK_BEAM_INFO.urukul_device,
        )
        self.clock_shelving_shaped_pulse: BlackmanShapedPulse

        self.clock_shelving_shaped_pulse.bind_param(
            "pulse_duration", self.shelving_pulse_time
        )

    @kernel
    def fire_clock_shelving_pulse(self):
        self.clock_shelving_shaped_pulse.trigger_pulse()

    @kernel
    def post_dipole_trap_hook(self):
        # set up ram mode
        self.post_dipole_trap_hook_shaped_pulses()
        delay_mu(int64(self.core.ref_multiplier))
        # do shelving and clearout
        self.post_dipole_trap_hook_default()
        delay_mu(int64(self.core.ref_multiplier))
        self.post_dipole_trap_hook_shelving_and_clearout()
        # disable ram mode after shelving and clearout
        self.clock_shelving_shaped_pulse.disable_ram_mode()
        # re-set the AOM to default
        self.clock_default_setter.turn_on_all(light_enabled=False)

    @kernel
    def post_dipole_trap_hook_shaped_pulses(self):
        """
        Before shelving in the dipole trap, set up the clock beam for RAM
        mode
        """
        self.clock_shelving_shaped_pulse.prepare_pulse(
            frequency=CLOCK_BEAM_INFO.frequency
        )
