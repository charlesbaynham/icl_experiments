"""
Global-parameter symmetric Mach-Zehnder mixin for the declarative LMT stack.

The per-pulse declarative engine (:mod:`repository.lib.lmt_sequence` +
:class:`~repository.lib.experiment_templates.mixins.declarative_lmt.DeclarativeLMTCoreBase`)
spawns one detuning-offset and one duration parameter per pulse, which is ideal
for commissioning a fixed sequence but unwieldy for routine running. This mixin
runs the engine in global-parameter mode
(``lmt_use_per_pulse_params = False``): the standard velocity-selected launch +
symmetric Mach-Zehnder interferometer is generated procedurally from a handful
of shared knobs - launch-pulse and LMT-recoil counts, per-beam detunings and
durations, the delivery set points and the dark times - and every pulse's
offset / duration / set-point slot is bound to the relevant shared handle.

The two counts are read once per run in ``host_setup`` and must NOT be placed on
a scan axis: they change the number of events, and the per-event kernel arrays
are ``kernel_invariants`` (constant across a scan). Everything else (detunings,
durations, set points, dark times) is freely scannable.

Compose it above one of the concrete release bases, e.g.
:class:`~repository.lib.experiment_templates.mixins.declarative_lmt.DeclarativeLMTBase`.
See :mod:`repository.lib.lmt_sequence` for the generated interferometer shape
(:func:`~repository.lib.lmt_sequence.symmetric_mach_zehnder_sequence`).
"""

import logging
import math

from artiq.language import kernel
from artiq.language import portable
from ndscan.experiment.parameters import BoolParam
from ndscan.experiment.parameters import BoolParamHandle
from ndscan.experiment.parameters import FloatParam
from ndscan.experiment.parameters import FloatParamHandle
from ndscan.experiment.parameters import IntParam
from ndscan.experiment.parameters import IntParamHandle

from repository.lib import constants
from repository.lib.experiment_templates.mixins.declarative_lmt import (
    DeclarativeLMTCoreBase,
)
from repository.lib.lmt_sequence import EVENT_PULSE
from repository.lib.lmt_sequence import EVENT_SETPOINT
from repository.lib.lmt_sequence import SequenceError
from repository.lib.lmt_sequence import symmetric_mach_zehnder_sequence
from repository.lib.physics.lmt_resonance import GROUND

logger = logging.getLogger(__name__)

CLOCK_BEAM_DELIVERY_INFO = constants.SUSERVOED_BEAMS["clock_delivery"]

# Index of the slice SetPoint in the generated sequence (it is always the first
# event). The full-intensity SetPoint follows; both share the single delivery
# AOM, so all launch and interferometer pulses run at one set point.
_SLICE_SETPOINT_INDEX = 0


@portable
def derived_dark_times(mean_dark_time, imbalance):
    """Split a constant total interrogation time into two opposed dark periods.

    Holds ``dark1 + dark2 = 2 * mean_dark_time`` while opening the
    interferometer by ``imbalance``::

        dark1 = mean_dark_time - imbalance / 2
        dark2 = mean_dark_time + imbalance / 2

    Sweeping ``imbalance`` at fixed ``mean_dark_time`` separates the two output
    wavepackets by ``v_rec * imbalance`` at the final beam splitter while the
    total interrogation time - and every time-dependent decoherence channel -
    is held constant, isolating wavepacket overlap from time-dependent
    dephasing. ``imbalance`` may be negative; ``|imbalance| <= 2 * mean``
    keeps both dark periods non-negative.
    """
    half = imbalance / 2.0
    return mean_dark_time - half, mean_dark_time + half


class LMTGlobalParamsSymmetricMachZehnderMixin(DeclarativeLMTCoreBase):
    """Drive the declarative LMT engine from a compact set of global knobs.

    See the module docstring. Provides the global parameters, the procedural
    sequence generator (:meth:`lmt_make_sequence`) and the slot-binding hooks the
    engine calls in global mode.
    """

    lmt_use_per_pulse_params = False

    # Atoms are released from the trap in the ground state with no kicks
    lmt_initial_population = {(GROUND, 0)}

    def build_fragment(self):
        super().build_fragment()

        # Set-once counts: read once in host_setup; do NOT scan (they change the
        # number of events, and the per-event arrays are kernel_invariants).
        self.setattr_param(
            "lmt_n_launch_pulses",
            IntParam,
            "Number of launch ladder pulses (set once per run; not scannable)",
            default=constants.LMT_N_LAUNCH_DEFAULT,
            min=0,
            is_scannable=False,
        )
        self.lmt_n_launch_pulses: IntParamHandle

        self.setattr_param(
            "lmt_n_recoils",
            IntParam,
            "Number of LMT-enhanced recoils added to each arm in each half of "
            "the interferometer (set once per run; not scannable)",
            default=constants.LMT_N_RECOILS_DEFAULT,
            min=0,
            is_scannable=False,
        )
        self.lmt_n_recoils: IntParamHandle

        # Set-once like the counts (it changes the event count via inserted
        # clearout/wait pairs), so is_scannable=False and read in host_setup.
        self.setattr_param(
            "lmt_clearout_both_excited",
            BoolParam,
            "Insert clearouts automatically",
            default=False,
            is_scannable=False,
        )
        self.lmt_clearout_both_excited: BoolParamHandle

        # Per-beam detuning offsets (added to the model-predicted resonance)
        self.setattr_param(
            "lmt_up_offset",
            FloatParam,
            "Detuning offset shared by all full-intensity up-beam pulses",
            default=0.0,
            unit="kHz",
        )
        self.lmt_up_offset: FloatParamHandle

        self.setattr_param(
            "lmt_down_offset",
            FloatParam,
            "Detuning offset shared by all full-intensity down-beam pulses",
            default=0.0,
            unit="kHz",
        )
        self.lmt_down_offset: FloatParamHandle

        self.setattr_param(
            "lmt_slice_offset",
            FloatParam,
            "Detuning offset of the velocity-selective slice pulse",
            default=0.0,
            unit="kHz",
        )
        self.lmt_slice_offset: FloatParamHandle

        # Per-beam pulse durations (override the Rabi-derived defaults)
        self.setattr_param(
            "lmt_up_duration",
            FloatParam,
            "Duration shared by all full-intensity up-beam pulses",
            default=constants.CLOCK_PI_TIME,
            unit="us",
            min=0.0,
        )
        self.lmt_up_duration: FloatParamHandle

        self.setattr_param(
            "lmt_down_duration",
            FloatParam,
            "Duration shared by all full-intensity down-beam pulses",
            default=constants.CLOCK_DOWN_PI_TIME,
            unit="us",
            min=0.0,
        )
        self.lmt_down_duration: FloatParamHandle

        self.setattr_param(
            "lmt_slice_duration",
            FloatParam,
            "Duration of the velocity-selective slice pulse",
            default=constants.CLOCK_SHELVING_PULSE_TIME,
            unit="us",
            min=0.0,
        )
        self.lmt_slice_duration: FloatParamHandle

        # Beam splitters (pi/2 events) get their own shared per-beam duration.
        # A pi/2 fired at full intensity for half the pi time is only an ideal
        # square-pulse approximation, so this is tunable independently of the pi
        # duration rather than tied to it. Same intensity as the pi pulses (one
        # shared set point), so the declared Rabi frequency is unchanged.
        self.setattr_param(
            "lmt_up_pi2_duration",
            FloatParam,
            "Duration shared by all full-intensity up-beam pi/2 pulses "
            "(beam splitters)",
            default=constants.CLOCK_PI_TIME / 2,
            unit="us",
            min=0.0,
        )
        self.lmt_up_pi2_duration: FloatParamHandle

        self.setattr_param(
            "lmt_down_pi2_duration",
            FloatParam,
            "Duration shared by all full-intensity down-beam pi/2 pulses "
            "(beam splitters)",
            default=constants.CLOCK_DOWN_PI_TIME / 2,
            unit="us",
            min=0.0,
        )
        self.lmt_down_pi2_duration: FloatParamHandle

        # Delivery-AOM set points (one device, so launch and interferometer
        # share a single full-intensity set point; the slice runs lower)
        self.setattr_param(
            "lmt_full_setpoint",
            FloatParam,
            "Delivery AOM set point for the launch and interferometer pulses",
            default=CLOCK_BEAM_DELIVERY_INFO.setpoint,
            unit="V",
            min=0.0,
        )
        self.lmt_full_setpoint: FloatParamHandle

        self.setattr_param(
            "lmt_slice_setpoint",
            FloatParam,
            "Delivery AOM set point for the velocity-selective slice pulse",
            default=constants.CLOCK_SHELVING_PULSE_SETPOINT,
            unit="V",
            min=0.0,
        )
        self.lmt_slice_setpoint: FloatParamHandle

        # Dark times (the two free-evolution periods, symmetric about the mirror)
        self.setattr_param(
            "lmt_dark_time_1",
            FloatParam,
            "First interferometer dark time",
            default=constants.DELAY_BETWEEN_INTERFEROMETRY_PULSES,
            unit="us",
            min=0.0,
        )
        self.lmt_dark_time_1: FloatParamHandle

        self.setattr_param(
            "lmt_dark_time_2",
            FloatParam,
            "Second interferometer dark time",
            default=constants.DELAY_BETWEEN_INTERFEROMETRY_PULSES,
            unit="us",
            min=0.0,
        )
        self.lmt_dark_time_2: FloatParamHandle

        # Constant-total-time imbalance mode. When enabled, the two dark times
        # are overwritten each shot from a common mean and an opening imbalance
        # (see derived_dark_times); lmt_dark_time_1/2 must NOT also be scanned in
        # this mode, as the derived values would clobber the scan. Kept off by
        # default so the independent dark times above behave exactly as before.
        self.setattr_param(
            "lmt_use_derived_dark_times",
            BoolParam,
            "Derive the two dark times from a constant total time and an "
            "imbalance (set once per run; not scannable)",
            default=False,
            is_scannable=False,
        )
        self.lmt_use_derived_dark_times: BoolParamHandle

        self.setattr_param(
            "lmt_dark_time_mean",
            FloatParam,
            "Mean of the two dark times (half the total interrogation time); "
            "used only when lmt_use_derived_dark_times is set",
            default=constants.DELAY_BETWEEN_INTERFEROMETRY_PULSES,
            unit="us",
            min=0.0,
        )
        self.lmt_dark_time_mean: FloatParamHandle

        self.setattr_param(
            "lmt_dark_time_imbalance",
            FloatParam,
            "Dark-time imbalance dark2 - dark1 (the interferometer opening); "
            "used only when lmt_use_derived_dark_times is set. Keep "
            "|imbalance| <= 2 * mean so both dark periods stay non-negative",
            default=0.0,
            unit="us",
            min=None,
            max=None,
        )
        self.lmt_dark_time_imbalance: FloatParamHandle

        self.setattr_param(
            "lmt_interferometry_phase",
            FloatParam,
            "Phase of the interferometry pulses",
            default=0.0,
            unit="turns",
            scale=1,
            min=None,
            max=None,
        )
        self.lmt_interferometry_phase: FloatParamHandle

    def lmt_make_sequence(self) -> list:
        n_launch = self.lmt_n_launch_pulses.get()
        n_recoils = self.lmt_n_recoils.get()
        # The declared Rabi frequencies set the compile-time defaults and feed
        # the kernel's AC-Stark term; derive them from the duration knobs so a pi
        # pulse of that duration has the declared Rabi frequency.
        return symmetric_mach_zehnder_sequence(
            n_launch=n_launch,
            n_recoils=n_recoils,
            slice_setpoint=self.lmt_slice_setpoint.get(),
            slice_rabi_up=1.0 / (2.0 * self.lmt_slice_duration.get()),
            full_setpoint=self.lmt_full_setpoint.get(),
            rabi_up=1.0 / (2.0 * self.lmt_up_duration.get()),
            rabi_down=1.0 / (2.0 * self.lmt_down_duration.get()),
            dark_param_1="lmt_dark_time_1",
            dark_param_2="lmt_dark_time_2",
            phase_param="lmt_interferometry_phase",
            clearout_both_excited=self.lmt_clearout_both_excited.get(),
        )

    def host_setup(self):
        super().host_setup()
        # Cache the two dark-time param stores so the per-shot kernel hook can
        # overwrite their values directly (the engine reads the same stores via
        # the dark Wait handles' .get()). Bound unconditionally so the kernel
        # attributes always exist; only used when derived mode is enabled.
        self._lmt_dark_store_1 = self.lmt_dark_time_1._store
        self._lmt_dark_store_2 = self.lmt_dark_time_2._store

    @kernel
    def _lmt_pre_sequence_hook(self):
        if self.lmt_use_derived_dark_times.get():
            dark1, dark2 = derived_dark_times(
                self.lmt_dark_time_mean.get(),
                self.lmt_dark_time_imbalance.get(),
            )
            self._lmt_dark_store_1.set_value(dark1)
            self._lmt_dark_store_2.set_value(dark2)

    @staticmethod
    def _is_slice_pulse(event) -> bool:
        return event.governing_setpoint_index == _SLICE_SETPOINT_INDEX

    @staticmethod
    def _is_pi2_pulse(event) -> bool:
        return math.isclose(event.area, 0.5)

    @staticmethod
    def _is_pi_pulse(event) -> bool:
        return math.isclose(event.area, 1.0)

    def lmt_global_offset_attr(self, event) -> "str | None":
        if event.kind != EVENT_PULSE:
            return None
        if self._is_slice_pulse(event):
            return "lmt_slice_offset"
        return "lmt_up_offset" if event.beam_sign > 0 else "lmt_down_offset"

    def lmt_global_duration_attr(self, event) -> "str | None":
        if event.kind != EVENT_PULSE:
            return None
        if self._is_slice_pulse(event):
            return "lmt_slice_duration"
        # Bind by area explicitly, and refuse anything we do not recognise rather
        # than falling through to the pi handle: a silent pi/2 -> pi fall-through
        # is exactly what fired the beam splitters as full pi pulses.
        if self._is_pi2_pulse(event):
            return (
                "lmt_up_pi2_duration"
                if event.beam_sign > 0
                else "lmt_down_pi2_duration"
            )
        if self._is_pi_pulse(event):
            return "lmt_up_duration" if event.beam_sign > 0 else "lmt_down_duration"
        raise SequenceError(
            f"Event {event.index}: global-parameter mode has no duration handle "
            f"for a full-intensity pulse of area {event.area:g} pi. Only pi and "
            "pi/2 pulses are supported; add a dedicated handle for this area or "
            "run the sequence in per-pulse mode."
        )

    def lmt_global_setpoint_attr(self, event) -> "str | None":
        if event.kind != EVENT_SETPOINT:
            return None
        if event.index == _SLICE_SETPOINT_INDEX:
            return "lmt_slice_setpoint"
        return "lmt_full_setpoint"
