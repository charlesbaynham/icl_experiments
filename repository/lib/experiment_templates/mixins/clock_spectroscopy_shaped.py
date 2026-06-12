import logging

from artiq.language import delay_mu
from artiq.language import kernel
from numpy import int64

from repository.lib.experiment_templates.mixins.clock_shelving import (
    ClockShelvingAndClearoutDipoleTrapMixin,
)
from repository.lib.experiment_templates.mixins.clock_spectroscopy import (
    CLOCK_UP_BEAM_INFO,
)
from repository.lib.experiment_templates.mixins.clock_spectroscopy import (
    ClockRabiSpectroscopyDipoleTrapMixin,
)
from repository.lib.fragments.checkpoint_fragment import RedMOTCheckpoints
from repository.lib.fragments.pulse_shaping import JessePulse

logger = logging.getLogger(__name__)


class ShapedRabiSpectroscopyDipoleTrapMixin(ClockRabiSpectroscopyDipoleTrapMixin):
    """
    Sets up the clock beam for clock spectroscopy with a shaped pulse in a
    dipole trap

    Kernel hooks used (multiple mixins cannot use the same hooks):

    * :meth:`~before_start_hook`
    * :meth:`~do_first_pulse`
    * :meth:`~post_dipole_trap_hook`
    * :meth:`~post_sequence_cleanup_checkpoint`
    """

    def build_fragment(self):
        super().build_fragment()

        self.setattr_fragment(
            "clock_spectroscopy_shaped_pulse",
            JessePulse,
            ad9910_name=CLOCK_UP_BEAM_INFO.urukul_device,
        )
        self.clock_spectroscopy_shaped_pulse: JessePulse

        self.clock_spectroscopy_shaped_pulse.bind_param(
            "pulse_duration", self.spectroscopy_pulse_time
        )

        # Self-cascading cleanup: re-prepare the shaped clock pulse for RAM-mode
        # playback at the end of the sequence. Registered as a child
        # RedMOTCheckpoints subfragment so its post_sequence_cleanup_checkpoint
        # runs automatically via the cascade.
        class _ShapedPulsesCleanupFrag(RedMOTCheckpoints):
            def build_fragment(self, clock_spectroscopy_shaped_pulse: JessePulse):
                self.clock_spectroscopy_shaped_pulse = clock_spectroscopy_shaped_pulse
                self.kernel_invariants = getattr(self, "kernel_invariants", set())
                self.kernel_invariants.add("clock_spectroscopy_shaped_pulse")

            @kernel
            def post_sequence_cleanup_checkpoint(self):
                self.post_sequence_cleanup_checkpoint_subfragments()
                # set up the clock beam for RAM mode
                self.clock_spectroscopy_shaped_pulse.prepare_pulse(
                    frequency=CLOCK_UP_BEAM_INFO.frequency
                )

        self.setattr_fragment(
            "_shaped_pulses_cleanup",
            _ShapedPulsesCleanupFrag,
            clock_spectroscopy_shaped_pulse=self.clock_spectroscopy_shaped_pulse,
        )
        self._shaped_pulses_cleanup: _ShapedPulsesCleanupFrag

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
            frequency=CLOCK_UP_BEAM_INFO.frequency
        )


class ShapedClockShelvingAndClearoutDipoleTrapMixin(
    ClockShelvingAndClearoutDipoleTrapMixin
):
    def build_fragment(self):
        super().build_fragment()

        self.setattr_fragment(
            "clock_shelving_shaped_pulse",
            JessePulse,
            ad9910_name=CLOCK_UP_BEAM_INFO.urukul_device,
        )
        self.clock_shelving_shaped_pulse: JessePulse

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
        self.clock_default_setter._turn_on_ad9910s(light_enabled=False)

    @kernel
    def post_dipole_trap_hook_shaped_pulses(self):
        """
        Before shelving in the dipole trap, set up the clock beam for RAM
        mode
        """
        self.clock_shelving_shaped_pulse.prepare_pulse(
            frequency=CLOCK_UP_BEAM_INFO.frequency
        )
