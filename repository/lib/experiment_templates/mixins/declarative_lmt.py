"""
Execution mixin for declarative LMT sequences.

This is a new, parallel implementation of LMT pulse sequences driven by the
declaration language in :mod:`repository.lib.lmt_sequence`. It shares no code
with the legacy LMT stack in ``LMT_launch_mixins.py`` (which is preserved
unchanged and headed for deprecation); the two use the same kernel hook and
cannot be combined in one experiment.

The engine (:class:`DeclarativeLMTCoreBase`) is independent of how the atoms are
prepared; two concrete bases bind it to a release mechanism:

* :class:`DeclarativeLMTBase` - runs the declared sequence after release from
  the dipole trap
  (:class:`~repository.lib.experiment_templates.dipole_trap_experiment.DipoleTrapWithExperimentBase`).
* :class:`DeclarativeLMTRedMOTBase` - runs it directly from the red MOT
  (:class:`~repository.lib.experiment_templates.dma_actions_after_drop.DMAActionsAfterDropMixin`),
  for when the dipole laser is unavailable.

Principles
----------

- The whole pulse sequence is declared, including the velocity-selective
  pulse: it is a normal pulse, just longer and with a lower delivery set
  point.
- t=0 for the gravity Doppler is the moment the atoms are released, provided
  by the base's :meth:`~DeclarativeLMTCoreBase.get_doppler_t_ref_mu`: the
  dipole-trap drop (``t_dipole_beams_off``) for :class:`DeclarativeLMTBase`,
  red-MOT light-off for :class:`DeclarativeLMTRedMOTBase`. The atoms
  addressed by the velocity slice are already falling, so every pulse -
  including the slicer - carries the full Doppler term ``s * D(t)``
  accumulated since the release. Because the term is proportional to the beam
  sign ``s``, the pre-slice fall shifts the up and down beams asymmetrically
  (the legacy stack absorbed this into empirical per-beam offsets). Fired
  this way, an un-offset slicer selects the class that was at rest at the
  release, which is also the assumption the ballistic camera-ROI predictor
  makes (see
  :class:`~repository.lib.experiment_templates.mixins.andor_imaging.lmt_compensated_normalised_imaging.NormalisedFastKineticsLMTCorrectedMixin`,
  which reads the same release timestamp as its trajectory t=0).
- The switch AOMs stay at their nominal frequency and amplitude; they only
  gate pulses on and off.
- All frequency control happens on the OPLL offset DDS. Every pulse is fired
  at ``f = START + s * D(t) - m_term + offset`` where ``D(t)`` is the gravity
  Doppler (evaluated at the pulse centre) and ``m_term`` is the
  model-predicted resonance term of the addressed momentum class, including
  the photon-recoil energy - both are always applied.
  During each pulse the OPLL is chirped at the gravity rate so long pulses
  (e.g. the velocity-selective one) stay on resonance; the chirp crosses the
  model-predicted frequency at the pulse centre.
  Relative to the legacy formulas the recoil term shifts every pulse by
  ``-s * kick / 2`` (~4.7 kHz); per-pulse offset parameters (default 0)
  absorb any residual during commissioning.
- Beam intensity is controlled exclusively through the delivery AOM SUServo
  set point, which changes ONLY at
  :class:`~repository.lib.lmt_sequence.SetPoint` events: the engine writes
  the new value there and then waits ``clock_delivery_preempt_time`` for the
  servo to recapture before continuing, so pulses never carry hidden
  set-point writes or settling waits. Every ``SetPoint`` spawns a scannable
  ndscan parameter. GOTCHA: a ``SetPoint`` therefore costs time on the
  timeline. A ``SetPoint`` between an interferometer's beam splitters makes
  the dark times asymmetric and the interferometer will not close unless it
  is balanced on the other side of the mirror pulse - ideally by a mirrored
  ``SetPoint`` (re-declaring the current value costs exactly the same
  time). Note that the legacy stack instead varied the switch
  AOM's RF attenuation for low-intensity pulses
  (``LMT_launch_mixins.do_selective_lmt_pulse``); attenuation in dB has an
  uncalibrated nonlinear relationship to optical power, so equivalent set
  points must be calibrated on atoms when porting tuned values.
- Every atom-affecting event self-describes to the pulse recorder as it
  fires: pulses register their build-time intent (pi transfer or
  superposition of the resolved pair), clearouts and callbacks register
  theirs too, so the recorded intent stream always matches what actually ran
  (see :mod:`repository.lib.pulse_intent`).
"""

import abc
import logging

from artiq.language import at_mu
from artiq.language import delay
from artiq.language import delay_mu
from artiq.language import kernel
from artiq.language import now_mu
from artiq.language import portable
from ndscan.experiment.parameters import FloatParam
from ndscan.experiment.parameters import FloatParamHandle
from numpy import int32
from numpy import int64

from repository.lib import constants
from repository.lib.experiment_templates.dipole_trap_experiment import (
    DipoleTrapWithExperimentBase,
)
from repository.lib.experiment_templates.dma_actions_after_drop import (
    DMAActionsAfterDropMixin,
)
from repository.lib.experiment_templates.mixins.clock_opll_tracking import (
    ClockOPLLTrackingMixin,
)
from repository.lib.experiment_templates.mixins.clock_spectroscopy import (
    ClockSpectroscopyBase,
)
from repository.lib.lmt_sequence import EVENT_CLEAROUT
from repository.lib.lmt_sequence import EVENT_PULSE
from repository.lib.lmt_sequence import EVENT_SETPOINT
from repository.lib.lmt_sequence import EVENT_WAIT
from repository.lib.lmt_sequence import CompiledSequence
from repository.lib.lmt_sequence import compile_sequence
from repository.lib.physics import lmt_resonance

logger = logging.getLogger(__name__)

CLOCK_OPLL_BEAM_INFO = constants.URUKULED_BEAMS["698_clock_OPLL_offset"]

start_opll_offset = CLOCK_OPLL_BEAM_INFO.frequency
ramp_rate = constants.GRAVITY_DOPPLER_PER_SEC_CLOCK

# Doppler shift per unit initial velocity along the clock axis (1/lambda, in
# Hz per m/s). The v0 Doppler correction added to each pulse's OPLL centre
# frequency is -beam_sign * v0 * inverse_clock_wavelength (see run_lmt_sequence
# and repository.lib.physics.lmt_resonance.v0_doppler_term_hz for the sign
# derivation against the LMT_sim reference).
inverse_clock_wavelength = 1.0 / constants.CLOCK_WAVELENGTH_M


class DeclarativeLMTCoreBase(ClockOPLLTrackingMixin, ClockSpectroscopyBase, abc.ABC):
    """
    Engine that runs an LMT pulse sequence declared as a list of event
    dataclasses. Release-mechanism agnostic: use one of the concrete bases
    (:class:`DeclarativeLMTBase` for the dipole trap,
    :class:`DeclarativeLMTRedMOTBase` for release straight from the red MOT)
    rather than this class directly.

    Subclasses declare the sequence and the initial atomic population as
    class attributes. The sequence contains everything from the
    velocity-selective pulse onwards - the slicer is just a normal pulse
    with a longer duration and a lower delivery set point::

        class MyInterferometerFrag(DeclarativeLMTBase, ...):
            lmt_initial_population = {("g", 0)}
            lmt_sequence = [
                SetPoint(setpoint=0.012, rabi_up=1.3e3, label="slice"),
                pi(Beam.UP, m=0, label="slice"),
                SetPoint(setpoint=2.6, rabi_up=9.1e3, rabi_down=7.4e3),
                Clearout(),
                *ladder(start_m=1, n=12, first_beam=Beam.DOWN),
                ...
            ]

    t=0 for the gravity Doppler is the moment the atoms are released, read
    each shot from :meth:`get_doppler_t_ref_mu`, which the concrete base
    implements in the timebase its pulses fire in. The same release time is
    used by the trajectory-corrected camera-ROI machinery, keeping the
    frequency bookkeeping and the imaging predictions consistent.

    At build time the sequence is validated (momentum-class bookkeeping, see
    :func:`~repository.lib.lmt_sequence.compile_sequence`) and one ndscan
    parameter is spawned per knob: a detuning offset (default 0, relative to
    the model-predicted resonance) and a duration (default derived from the
    declared Rabi frequency) per pulse, a set point per
    :class:`~repository.lib.lmt_sequence.SetPoint`, and durations for waits
    and clearouts. The compiled per-event intent (pi transfer or
    superposition of the resolved pair, momentum kick) is shipped to the
    kernel and registered with the pulse recorder as each event fires.

    Callback events dispatch to :meth:`lmt_sequence_callback`, which
    subclasses override with an ``if``/``elif`` on the callback id (ARTIQ
    kernels have no function pointers).
    """

    lmt_sequence: list = None
    lmt_initial_population: set = None
    lmt_strict_validation: bool = True

    def build_fragment(self):
        super().build_fragment()

        # The clock OPLL device (_clock_opll) and the set_clock_opll /
        # start_clock_opll_ramp / stop_clock_opll_ramp wrappers come from
        # ClockOPLLTrackingMixin.

        # Required by ClockSpectroscopyBase.prepare_clock_delivery_aom
        if not hasattr(self, "spectroscopy_pulse_time"):
            self.setattr_param(
                "spectroscopy_pulse_time",
                FloatParam,
                "Duration of an up beam pulse",
                default=constants.CLOCK_PI_TIME,
                unit="us",
            )
            self.spectroscopy_pulse_time: FloatParamHandle

        self.setattr_param(
            "clearout_duration",
            FloatParam,
            "Duration of 461 clearout pulses in the LMT sequence",
            default=constants.LMT_PULSE_CLEAROUT_DURATION,
            unit="us",
            min=0.0,
        )
        self.clearout_duration: FloatParamHandle

        # Initial-velocity (v0) Doppler and probe (AC-Stark) shift corrections,
        # both applied to the OPLL centre frequency of every pulse (see
        # run_lmt_sequence). These are calibratable physics constants the model
        # previously dropped relative to the LMT_sim reference; defaults are the
        # calibrated values but fully overridable / scannable.
        self.setattr_param(
            "lmt_initial_velocity",
            FloatParam,
            "Initial (release) z-velocity v0 of the velocity-selected class, "
            "positive upward. Adds -beam_sign*v0/lambda to each pulse's OPLL "
            "centre frequency (opposite sign up vs down).",
            default=lmt_resonance.DEFAULT_INITIAL_VELOCITY_M_S,
            unit="mm/s",
            scale=1e-3,
        )
        self.lmt_initial_velocity: FloatParamHandle

        self.setattr_param(
            "lmt_probe_stark_alpha",
            FloatParam,
            "Probe (AC-Stark) shift coefficient alpha. Each pulse's OPLL centre "
            "frequency is shifted by -alpha*rabi**2 (rabi = declared Rabi at the "
            "governing set point).",
            default=lmt_resonance.DEFAULT_PROBE_STARK_ALPHA_HZ_S2,
            unit="",
        )
        self.lmt_probe_stark_alpha: FloatParamHandle

        if not self.lmt_sequence:
            raise TypeError(
                f"{type(self).__name__} must declare a non-empty 'lmt_sequence' "
                "class attribute"
            )
        if not self.lmt_initial_population:
            raise TypeError(
                f"{type(self).__name__} must declare a non-empty "
                "'lmt_initial_population' class attribute, e.g. {('e', 1)}"
            )

        # Build-time validation happens here
        compiled = compile_sequence(
            list(self.lmt_sequence),
            initial_population=set(self.lmt_initial_population),
            strict=self.lmt_strict_validation,
        )
        self._lmt_compiled: CompiledSequence = compiled
        logger.info(
            "Compiled LMT sequence with %d events; final population: %s",
            len(compiled.events),
            sorted(compiled.final_population),
        )

        # The kernel cannot iterate a list of heterogeneous event objects (no
        # dataclasses/sum types across the host->kernel boundary), so each event
        # is shipped as a slot in several parallel, same-length, same-type
        # arrays instead. Events that do not own a given parameter still need a
        # slot in that array, so they get this dummy "pad" handle. Do not try to
        # "tidy" this into a list of per-event objects - the ARTIQ compiler
        # cannot consume that.
        pad_handle = self.setattr_param(
            "lmt_unused_pad",
            FloatParam,
            "Padding parameter for the LMT sequence engine - ignored, do not scan",
            default=0.0,
        )
        self.lmt_unused_pad: FloatParamHandle
        self.override_param("lmt_unused_pad", initial_value=0.0)

        # Parallel per-event arrays read by the kernel. NB no bool lists:
        # the ARTIQ compiler quotes host lists of Python bools as integer
        # lists (bool is an int subclass); beam direction is carried as a
        # float sign and compared in the kernel instead.
        self._lmt_n_events = len(compiled.events)
        self._lmt_event_kind = []
        self._lmt_beam_sign = []
        self._lmt_m_term_hz = []
        # Declared Rabi frequency (Hz) per pulse at its governing set point,
        # used by the kernel for the probe (AC-Stark) shift. 0.0 for non-pulse
        # events.
        self._lmt_rabi_hz = []
        self._lmt_callback_id = []
        self._lmt_offset_handles = []
        self._lmt_duration_handles = []
        self._lmt_setpoint_handles = []
        # Build-time intent shipped to the kernel and registered with the
        # pulse recorder as each event fires (integer codes from
        # repository.lib.pulse_intent, filled in by the sequence compiler)
        self._lmt_intent_state_effect = []
        self._lmt_intent_addressed_state = []
        self._lmt_intent_addressed_m = []
        self._lmt_intent_delta_m = []
        self._lmt_intent_duration_s = []
        # (slot index, fragment attribute name) pairs resolved in host_setup,
        # because the referenced parameter may be created by a mixin that
        # builds after this one in the MRO.
        self._lmt_duration_param_refs = []

        for event in compiled.events:
            self._lmt_event_kind.append(int32(event.kind))
            self._lmt_beam_sign.append(float(event.beam_sign))
            self._lmt_m_term_hz.append(float(event.m_term_hz))
            self._lmt_rabi_hz.append(float(event.rabi_hz))
            self._lmt_callback_id.append(int32(event.callback_id))
            self._lmt_intent_state_effect.append(int32(event.state_effect))
            self._lmt_intent_addressed_state.append(int32(event.addressed_state))
            self._lmt_intent_addressed_m.append(int32(event.addressed_m))
            self._lmt_intent_delta_m.append(int32(event.delta_m))
            self._lmt_intent_duration_s.append(float(event.declared_duration_s))

            if event.offset_param is not None:
                handle = self.setattr_param(
                    event.offset_param.attr_name,
                    FloatParam,
                    event.offset_param.description,
                    default=event.offset_param.default,
                    unit=event.offset_param.unit,
                )
                self._lmt_offset_handles.append(handle)
            else:
                self._lmt_offset_handles.append(pad_handle)

            if event.duration_param is not None:
                spec = event.duration_param
                handle = self.setattr_param(
                    spec.attr_name,
                    FloatParam,
                    spec.description,
                    default=spec.default,
                    unit=spec.unit,
                    min=spec.min,
                )
                self._lmt_duration_handles.append(handle)
            elif event.duration_param_ref is not None:
                self._lmt_duration_param_refs.append(
                    (len(self._lmt_duration_handles), event.duration_param_ref)
                )
                self._lmt_duration_handles.append(pad_handle)
            else:
                self._lmt_duration_handles.append(pad_handle)

            if event.setpoint_param is not None:
                spec = event.setpoint_param
                handle = self.setattr_param(
                    spec.attr_name,
                    FloatParam,
                    spec.description,
                    default=spec.default,
                    unit=spec.unit,
                    min=spec.min,
                )
                self._lmt_setpoint_handles.append(handle)
            else:
                self._lmt_setpoint_handles.append(pad_handle)

        self.kernel_invariants = getattr(self, "kernel_invariants", set()) | {
            "_lmt_n_events",
            "_lmt_event_kind",
            "_lmt_beam_sign",
            "_lmt_m_term_hz",
            "_lmt_rabi_hz",
            "_lmt_callback_id",
            "_lmt_intent_state_effect",
            "_lmt_intent_addressed_state",
            "_lmt_intent_addressed_m",
            "_lmt_intent_delta_m",
            "_lmt_intent_duration_s",
        }

    def host_setup(self):
        super().host_setup()

        # Late resolution of duration parameters that reference existing
        # handles (Wait(param=...) and shared clearouts): the referenced
        # parameter may only exist after every mixin has built.
        for slot, attr_name in self._lmt_duration_param_refs:
            handle = getattr(self, attr_name, None)
            if not isinstance(handle, FloatParamHandle):
                raise TypeError(
                    f"LMT sequence event {slot} references parameter "
                    f"'{attr_name}', which is not a FloatParamHandle on "
                    f"{type(self).__name__} (got {type(handle).__name__})"
                )
            self._lmt_duration_handles[slot] = handle

    # set_clock_opll / start_clock_opll_ramp / stop_clock_opll_ramp come from
    # ClockOPLLTrackingMixin (they drive _clock_opll and update the
    # frequency-tracking state read by PulseDMARecording.register_pulse).

    # ------------------------------------------------------------------
    # Sequence execution
    # ------------------------------------------------------------------

    @abc.abstractmethod
    def get_doppler_t_ref_mu(self) -> int64:
        """
        Timeline position of the atoms' release - t=0 for the gravity
        Doppler of every pulse in the declared sequence.

        Implemented by the concrete bases as a ``@portable`` method, in the
        same timebase that ``now_mu()`` reads when the sequence fires (for
        DMA-recorded sequences that is the recording-relative timebase).
        """
        raise NotImplementedError

    @kernel
    def _set_delivery_setpoint(self, setpoint_v: float):
        """Write the delivery AOM SUServo set point (tracked)."""
        self.set_clock_delivery_aom(
            freq=self.calculate_clock_delivery_freq(now_mu(), 0.0),
            setpoint_v=setpoint_v,
        )

    @kernel
    def _prepare_switch_dds_nominal(self):
        """Set both switch DDSes to nominal frequency and amplitude.

        The switches only gate pulses on and off; all frequency control
        happens on the OPLL.
        """
        self.set_clock_up_dds(
            frequency=self.clock_switch_frequency_handle.get(),
            amplitude=self.clock_switch_amplitude_handle.get(),
        )
        delay_mu(8)
        self.set_clock_down_dds(
            frequency=self.clock_switch_frequency_handle.get(),
            amplitude=self.clock_switch_amplitude_handle.get(),
        )
        delay_mu(8)

    @kernel
    def _fire_pulse(
        self,
        freq_centre: float,
        t_start: int64,
        is_up: bool,
        duration: float,
        state_effect: int32,
        addressed_state: int32,
        addressed_m: int32,
        delta_m: int32,
    ):
        """Fire one pulse gated by the switch AOM, registering its intent.

        The OPLL is chirped at the gravity rate for the duration of the
        pulse so that long pulses stay on resonance with the falling atoms;
        the chirp crosses ``freq_centre`` at the centre of the pulse. The
        ramp is programmed before ``t_start``, so it starts running slightly
        early - at ~14 MHz/s the resulting frequency error is negligible.

        The intent arguments are the compile-time-resolved effect of the
        pulse (see :mod:`repository.lib.pulse_intent`), registered with the
        pulse recorder alongside the pulse facts.
        """
        self.stop_clock_opll_ramp()
        delay_mu(8)
        if is_up:
            # The resonance drifts upwards for the up beam
            f_on = freq_centre - ramp_rate * duration / 2
            self.start_clock_opll_ramp(ramp_rate, f_on, f_on + 2e6, wave_type=1)
        else:
            # ... and downwards for the down beam (wave_type 2 ramps down
            # from freq_high)
            f_on = freq_centre + ramp_rate * duration / 2
            self.start_clock_opll_ramp(ramp_rate, f_on - 2e6, f_on, wave_type=2)

        at_mu(t_start)
        self.register_pulse_with_intent(
            is_up=is_up,
            duration_s=duration,
            state_effect=state_effect,
            addressed_state=addressed_state,
            addressed_m=addressed_m,
            delta_m=delta_m,
        )
        if is_up:
            self.clock_up_dds.sw.on()
            delay(duration)
            self.clock_up_dds.sw.off()
        else:
            self.clock_down_dds.sw.on()
            delay(duration)
            self.clock_down_dds.sw.off()
        delay_mu(8)
        self.stop_clock_opll_ramp()
        delay(10e-6)

    @kernel
    def lmt_sequence_callback(self, callback_id: int32):
        """Dispatch target for Callback events. Override in the experiment.

        Subclasses dispatch on the id::

            @kernel
            def lmt_sequence_callback(self, callback_id: int32):
                if callback_id == 1:
                    self.my_shaped_pulse()
                else:
                    raise ValueError("Unknown LMT sequence callback id")

        The engine registers the Callback's declared intent (its
        ``state_effect``/``delta_m``/``duration``) with the pulse recorder
        immediately BEFORE dispatching here, so the fired pulse
        self-describes even though it bypasses the square-pulse path. The
        implementation must therefore NOT also call ``register_pulse`` /
        ``register_pulse_with_intent`` / ``register_intent_callback`` -
        doing so would double-count the event in the intent stream.
        """
        raise ValueError(
            "Unhandled LMT sequence Callback - override lmt_sequence_callback() "
            "in the experiment class and dispatch on the callback id"
        )

    @kernel
    def run_lmt_sequence(self):
        """Execute the declared sequence.

        The gravity Doppler of every pulse is referenced to the atoms'
        release (:meth:`get_doppler_t_ref_mu`): the atoms addressed by the
        velocity-selective pulse are already falling, so the slicer too
        carries its accumulated Doppler term, and an un-offset slicer
        selects the class that was at rest at the release.

        The delivery set point changes only at SETPOINT events, each of
        which waits ``clock_delivery_preempt_time`` for the servo to
        recapture; pulses never touch the set point.

        Every atom-affecting event registers its intent with the pulse
        recorder as it fires: pulses via
        :meth:`~repository.lib.experiment_templates.red_mot_experiment.RedMOTWithExperimentBase.register_pulse_with_intent`,
        clearouts via ``register_clearout`` and callbacks via
        ``register_intent_callback``.
        """
        t_ref_mu = self.get_doppler_t_ref_mu()

        for i in range(self._lmt_n_events):
            kind = self._lmt_event_kind[i]

            if kind == EVENT_PULSE:
                duration = self._lmt_duration_handles[i].get()
                # Margin for programming the OPLL ramp before the switch opens
                t_start = now_mu() + self.core.seconds_to_mu(10e-6)
                t_centre_mu = t_start + self.core.seconds_to_mu(duration / 2)

                # Gravity Doppler evaluated at the pulse centre, accumulated
                # since the release
                t_fall = self.core.mu_to_seconds(t_centre_mu - t_ref_mu)
                # Initial-velocity (v0) Doppler: opposite-signed up vs down,
                # the same sign as the gravity Doppler carries it (the OPLL
                # frequency picks up +beam_sign*(-v0/lambda); see
                # lmt_resonance.v0_doppler_term_hz). The gravity term assumes
                # v=0 at release, so this is the missing static piece.
                v0_doppler = (
                    -self._lmt_beam_sign[i]
                    * self.lmt_initial_velocity.get()
                    * inverse_clock_wavelength
                )
                # Probe (AC-Stark) shift: -alpha * rabi**2, with rabi the
                # declared intensity-derived value at the governing set point.
                rabi = self._lmt_rabi_hz[i]
                stark = -self.lmt_probe_stark_alpha.get() * rabi * rabi
                freq_centre = (
                    start_opll_offset
                    + self._lmt_beam_sign[i] * t_fall * ramp_rate
                    - self._lmt_m_term_hz[i]
                    + v0_doppler
                    + stark
                    + self._lmt_offset_handles[i].get()
                )
                self._fire_pulse(
                    freq_centre,
                    t_start,
                    self._lmt_beam_sign[i] > 0.0,
                    duration,
                    self._lmt_intent_state_effect[i],
                    self._lmt_intent_addressed_state[i],
                    self._lmt_intent_addressed_m[i],
                    self._lmt_intent_delta_m[i],
                )

            elif kind == EVENT_WAIT:
                delay(self._lmt_duration_handles[i].get())

            elif kind == EVENT_CLEAROUT:
                clearout_duration = self._lmt_duration_handles[i].get()
                self.register_clearout(duration_s=clearout_duration)
                self.fluorescence_pulse.do_clearout_pulse(
                    duration=clearout_duration,
                    ignore_final_shutters=True,
                )
                delay(8e-9)

            elif kind == EVENT_SETPOINT:
                # The only place the delivery set point changes. Write the
                # new value, then wait for the servo to recapture before
                # anything else happens. NB this advances the timeline:
                # inside an interferometer it must be balanced by a mirrored
                # SetPoint (or equal Wait) on the other side of the mirror
                # pulse, or the interferometer will not close.
                self._set_delivery_setpoint(self._lmt_setpoint_handles[i].get())
                delay(self.clock_delivery_preempt_time.get())

            else:  # EVENT_CALLBACK
                # Register the declared intent first, so the custom pulse
                # self-describes; the callback implementation must not also
                # call register_* (see lmt_sequence_callback)
                self.register_intent_callback(
                    duration_s=self._lmt_intent_duration_s[i],
                    state_effect=self._lmt_intent_state_effect[i],
                    delta_m=self._lmt_intent_delta_m[i],
                )
                self.lmt_sequence_callback(self._lmt_callback_id[i])

    @kernel
    def post_sequence_cleanup_hook_declarative_lmt(self):
        # Stop any OPLL ramp and restore the nominal offset
        self.stop_clock_opll_ramp()
        self.set_clock_opll(start_opll_offset)


class DeclarativeLMTBase(DeclarativeLMTCoreBase, DipoleTrapWithExperimentBase):
    """
    Runs a declared LMT sequence after release from the dipole trap.

    t=0 for the gravity Doppler is the moment the atoms are dropped from
    the dipole trap, recorded by :meth:`post_dipole_trap_hook` as
    ``t_dipole_beams_off``. The same timestamp is read by the
    trajectory-corrected camera-ROI machinery, keeping the frequency
    bookkeeping and the imaging predictions consistent. Because the dipole
    base DMA-records ``actions_after_drop`` (which contains both the stamp
    and the sequence), the stamp and every pulse share the
    recording-relative timebase.

    See :class:`DeclarativeLMTCoreBase` for the sequence language and engine.

    Kernel hooks used (multiple mixins cannot use the same hooks):

    * :meth:`~post_dipole_trap_hook`
    * :meth:`~do_experiment_after_dipole_trap_hook`

    In particular this means the legacy shelving mixin
    (``ClockShelvingAndClearoutDipoleTrapMixin``) cannot be combined with
    this one - velocity selection belongs in the declared sequence instead.
    """

    def build_fragment(self):
        super().build_fragment()

        # Timestamp of the dipole-trap drop, recorded each shot by
        # post_dipole_trap_hook; t=0 for the gravity Doppler and for the
        # ballistic camera-ROI predictor.
        self.t_dipole_beams_off = int64(0)

    @kernel
    def post_dipole_trap_hook(self):
        # Record the drop time: t=0 for the gravity Doppler of every pulse
        # and for the ballistic camera-ROI predictor
        self.t_dipole_beams_off = now_mu()
        self.post_dipole_trap_hook_default()

    @portable
    def get_doppler_t_ref_mu(self) -> int64:
        """The dipole-trap drop time stamped by :meth:`post_dipole_trap_hook`."""
        return self.t_dipole_beams_off

    @kernel
    def do_experiment_after_dipole_trap_hook(self):
        self.prepare_clock_delivery_aom()
        delay_mu(16)
        self._prepare_switch_dds_nominal()
        self.run_lmt_sequence()


class DeclarativeLMTRedMOTBase(DeclarativeLMTCoreBase, DMAActionsAfterDropMixin):
    """
    Runs a declared LMT sequence directly from the red MOT (no dipole trap),
    via :class:`~repository.lib.experiment_templates.dma_actions_after_drop.DMAActionsAfterDropMixin`.
    For when the 1064 nm dipole laser is unavailable.

    t=0 for the gravity Doppler is the red-MOT light-off (the atoms'
    release). The sequence runs inside the DMA-recorded
    ``actions_after_drop``, whose timeline cursor starts at zero at what
    will be the playback start - which run_once schedules ``expansion_time``
    AFTER light-off. In the recording-relative timebase the release
    therefore happened at ``-expansion_time``, which is what
    :meth:`get_doppler_t_ref_mu` returns (the ``pre_experiment_delay``
    between the post-drop actions and the experiment is *inside* the
    recording, so it needs no correction).

    See :class:`DeclarativeLMTCoreBase` for the sequence language and engine.

    Kernel hooks used (multiple mixins cannot use the same hooks):

    * :meth:`~do_experiment_after_drop_hook`
    """

    @portable
    def get_doppler_t_ref_mu(self) -> int64:
        """
        Release time in the recording-relative timebase the sequence runs in.

        run_once: light-off (release) -> delay(expansion_time) -> playback
        starts. The DMA recording's cursor starts at zero at the playback
        start, so the release sits at ``-expansion_time`` in the recording
        frame.
        """
        return -self.core.seconds_to_mu(self.expansion_time.get())

    @kernel
    def do_experiment_after_drop_hook(self):
        self.prepare_clock_delivery_aom()
        delay_mu(16)
        self._prepare_switch_dds_nominal()
        self.run_lmt_sequence()
