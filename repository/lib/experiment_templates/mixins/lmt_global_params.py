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
from repository.lib.lmt_sequence import symmetric_mach_zehnder_sequence
from repository.lib.physics.lmt_resonance import GROUND

logger = logging.getLogger(__name__)

CLOCK_BEAM_DELIVERY_INFO = constants.SUSERVOED_BEAMS["clock_delivery"]

# Index of the slice SetPoint in the generated sequence (it is always the first
# event). The full-intensity SetPoint follows; both share the single delivery
# AOM, so all launch and interferometer pulses run at one set point.
_SLICE_SETPOINT_INDEX = 0


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
        )

    @staticmethod
    def _is_slice_pulse(event) -> bool:
        return event.governing_setpoint_index == _SLICE_SETPOINT_INDEX

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
        return "lmt_up_duration" if event.beam_sign > 0 else "lmt_down_duration"

    def lmt_global_setpoint_attr(self, event) -> "str | None":
        if event.kind != EVENT_SETPOINT:
            return None
        if event.index == _SLICE_SETPOINT_INDEX:
            return "lmt_slice_setpoint"
        return "lmt_full_setpoint"
