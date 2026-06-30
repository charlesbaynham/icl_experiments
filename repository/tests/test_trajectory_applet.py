"""
Offline test harness for the LMT spacetime-trajectory applet.

Launches :mod:`repository.lib.applets.lmt_trajectory_applet` against a
synthetic ``pulse_intent_record`` so the applet can be exercised without any
hardware, kernel code or a live LMT shot.

The experiment is pure host code: it builds a configurable LMT sequence in the
declarative language (:mod:`repository.lib.lmt_sequence`), compiles it - so the
intent stream is exactly what the live recorder would emit - lays synthetic
timing over the compiled events, writes the result to the broadcast
``pulse_intent_record`` dataset (the same format
:class:`~repository.lib.fragments.pulse_recorder_and_tracker.PulseDMARecording`
emits) and issues a ``create_applet`` CCB command pointing the applet at it. Run
it from the dashboard (or ``artiq_run``) on any machine with the ARTIQ master
running -- no core device is touched.

The sequence is built from the submit arguments (see :func:`_build_sequence`):

* a velocity-selection pulse (always first),
* an optional pre-launch splitter (``do_split`` / ``n_split``) that forks the
  cloud into two spatially separated clouds of the same velocity class,
* an optional launch ladder of ``n_launch`` alternating-beam pi pulses (the
  large-momentum-transfer kicks), and
* an ``n_lmt``-recoil Mach-Zehnder interferometer (always; ``n_lmt = 1`` is a
  normal MZ), with ``interferometer_type`` selecting asymmetric (parallelogram)
  or symmetric (diamond) LMT geometry,

so one can dial up exactly the branch forking, solid/dotted state styling,
shaded pulses and clearout markers the applet should draw. ``include_gravity``
adds the free-fall parabola to the drawn positions.
"""

import logging

from artiq.experiment import BooleanValue
from artiq.experiment import EnumerationValue
from artiq.experiment import EnvExperiment
from artiq.experiment import NumberValue
from artiq.master.worker_impl import CCB

from repository.lib.lmt_sequence import EVENT_CALLBACK
from repository.lib.lmt_sequence import EVENT_CLEAROUT
from repository.lib.lmt_sequence import EVENT_PHASE
from repository.lib.lmt_sequence import EVENT_PULSE
from repository.lib.lmt_sequence import EVENT_SETPOINT
from repository.lib.lmt_sequence import EVENT_WAIT
from repository.lib.lmt_sequence import Beam
from repository.lib.lmt_sequence import Clearout
from repository.lib.lmt_sequence import Phase
from repository.lib.lmt_sequence import SetPoint
from repository.lib.lmt_sequence import Wait
from repository.lib.lmt_sequence import compile_sequence
from repository.lib.lmt_sequence import ladder
from repository.lib.lmt_sequence import pi
from repository.lib.lmt_sequence import pi2
from repository.lib.physics import lmt_resonance as pi_intent
from repository.lib.physics.lmt_resonance import EXCITED
from repository.lib.physics.lmt_resonance import GROUND

logger = logging.getLogger(__name__)

#: Field order of one row-major intent record, matching
#: ``PulseDMARecording._save_intent_record_to_dataset``.
_RECORD_KEYS = (
    "kind",
    "t_start_s",
    "duration_s",
    "state_effect",
    "addressed_state",
    "addressed_m",
    "delta_m",
)

#: Released from the trap in the ground state with no kicks.
_INITIAL_POPULATION = {(GROUND, 0)}

#: Dark-time default baked into the declared Wait events; the real value is
#: substituted per run when the compiled events are laid out in time.
_DARK_TIME_PLACEHOLDER = 1e-3


def _pulse(t_start, duration, effect, state, m, delta_m):
    return {
        "kind": pi_intent.Kind.PULSE,
        "t_start_s": t_start,
        "duration_s": duration,
        "state_effect": effect,
        "addressed_state": state,
        "addressed_m": m,
        "delta_m": delta_m,
    }


def _clearout(t_start, duration, state=pi_intent.AddressedState.GROUND):
    return {
        "kind": pi_intent.Kind.CLEAROUT,
        "t_start_s": t_start,
        "duration_s": duration,
        "state_effect": pi_intent.StateEffect.NONE,
        "addressed_state": state,
        "addressed_m": pi_intent.M_AUTO,
        "delta_m": 0,
    }


def _wait(t_start, duration):
    return {
        "kind": pi_intent.Kind.WAIT,
        "t_start_s": t_start,
        "duration_s": duration,
        "state_effect": pi_intent.StateEffect.NONE,
        "addressed_state": pi_intent.AddressedState.AUTO,
        "addressed_m": pi_intent.M_AUTO,
        "delta_m": 0,
    }


def _phase(t_start):
    return {
        "kind": pi_intent.Kind.PHASE,
        "t_start_s": t_start,
        "duration_s": 0.0,
        "state_effect": pi_intent.StateEffect.NONE,
        "addressed_state": pi_intent.AddressedState.AUTO,
        "addressed_m": pi_intent.M_AUTO,
        "delta_m": 0,
    }


def _record_from_events(events):
    """Pack a list of event dicts into the 7-row float record the applet reads."""
    return [[float(e[key]) for e in events] for key in _RECORD_KEYS]


def _populated(sequence):
    """The set of ``(state, m)`` the sequence so far leaves populated."""
    return compile_sequence(
        sequence, initial_population=_INITIAL_POPULATION
    ).final_population


def _top_pair(sequence):
    """The single ``(state, m)`` a single-chain sequence leaves populated."""
    return sorted(_populated(sequence))[0]


def _append_recombine(sequence):
    """Reconverge two spatially-separated split arms onto one momentum state.

    After equal acceleration the two arms sit one recoil apart and in opposite
    internal states - i.e. they are the two members of a pair
    ``(g, m_lo) <-> (e, m_hi)``. A pi/2 on that pair drops *both* arms into the
    same ``{(g, m_lo), (e, m_hi)}`` superposition; clearing the ground state then
    leaves both (still spatially separated) arms at the single excited momentum
    ``(e, m_hi)``. This is the real reconvergence trick - no swapping pi pulse.
    """
    arms = sorted(_populated(sequence), key=lambda sm: sm[1])
    ground = next(sm for sm in arms if sm[0] == GROUND)
    excited = next(sm for sm in arms if sm[0] == EXCITED)
    beam = Beam.UP if excited[1] == ground[1] + 1 else Beam.DOWN
    sequence.append(pi2(beam, m=ground[1], label="recombine"))
    sequence.append(Clearout(label="recombine-blast"))


def _raise_pulse(state, m):
    """A pi pulse raising a single arm by one recoil; returns (pulse, state, m)."""
    if state == GROUND:
        return pi(Beam.UP, m=m), EXCITED, m + 1
    return pi(Beam.DOWN, m=m), GROUND, m + 1


def _lower_pulse(state, m):
    """A pi pulse lowering a single arm by one recoil; returns (pulse, state, m)."""
    if state == GROUND:
        return pi(Beam.DOWN, m=m), EXCITED, m - 1
    return pi(Beam.UP, m=m), GROUND, m - 1


def _append_interferometer(sequence, *, state, m, n_lmt, symmetric):
    """Append a closing ``n_lmt``-recoil Mach-Zehnder on the pair at ``(state, m)``.

    The two arms are only ever addressed together as a clean one-recoil pair (for
    the mirror and recombiner). During each dark time an augment ladder widens the
    arms to ``n_lmt`` recoils and then collapses them back to the pair, so the
    interferometer always closes regardless of ``n_lmt``. ``n_lmt = 1`` is the
    ordinary pi/2 - pi - pi/2 MZ. ``symmetric=False`` (asymmetric) widens only the
    upper arm (a parallelogram); ``symmetric=True`` widens both arms in opposite
    directions (a diamond).
    """
    if n_lmt < 1:
        raise ValueError(
            f"N_LMT must be >= 1 (got {n_lmt}); 0 is not an interferometer"
        )

    beam = Beam.DOWN if state == EXCITED else Beam.UP
    sequence.append(pi2(beam, m=m, label="bs1"))
    # bs1 forks (state, m) into a lower arm a and an upper arm b one recoil up.
    a = [state, m]
    b = [GROUND if state == EXCITED else EXCITED, m + 1]

    def widen(label):
        for _ in range(n_lmt - 1):
            p, b[0], b[1] = _raise_pulse(b[0], b[1])
            sequence.append(p)
        if symmetric:
            for _ in range(n_lmt - 1):
                p, a[0], a[1] = _lower_pulse(a[0], a[1])
                sequence.append(p)
        sequence.append(Wait(t=_DARK_TIME_PLACEHOLDER, label=label))
        for _ in range(n_lmt - 1):
            p, b[0], b[1] = _lower_pulse(b[0], b[1])
            sequence.append(p)
        if symmetric:
            for _ in range(n_lmt - 1):
                p, a[0], a[1] = _raise_pulse(a[0], a[1])
                sequence.append(p)

    widen("dark1")
    sequence.append(pi(beam, m=m, label="mirror"))
    a[:], b[:] = b[:], a[:]  # the mirror swaps the two arms' (state, m)
    if a[1] > b[1]:
        a[:], b[:] = b[:], a[:]  # keep b as the upper arm for the second dark
    widen("dark2")
    sequence.append(pi2(beam, m=m, label="bs2"))


def _build_sequence(
    *,
    do_split,
    n_split,
    do_launch,
    n_launch,
    n_lmt,
    symmetric,
    pulse_duration,
    do_phase=False,
):
    """The declarative LMT sequence for the requested knobs.

    Structure, in firing order (mirrors the real experiment):

    1. Velocity selection (always): a pi pulse selects a velocity class,
       ``(g, 0) -> (e, 1)``, then a clearout blasts the unselected ground atoms.
    2. Optional pre-launch splitter: a pi/2 forks the cloud into two arms; an LMT
       ladder accelerates the upper arm; a dark time lets the arms separate in
       space; an equal-length ladder accelerates the lower arm; then a pi/2 +
       ground clearout reconverges both arms onto one momentum class while they
       stay spatially apart (see :func:`_append_recombine`).
    3. Optional launch: an LMT ladder accelerates the cloud(s) up together.
    4. Interferometer (always): an ``n_lmt``-recoil Mach-Zehnder on the resulting
       pair (``n_lmt = 1`` is the ordinary pi/2 - pi - pi/2 MZ); ``symmetric``
       selects the diamond vs parallelogram geometry. See
       :func:`_append_interferometer`.

    Returns the event list ready for :func:`compile_sequence`.
    """
    # The set point's declared Rabi only fixes the compiled default durations,
    # which we override with pulse_duration below; any positive value works.
    rabi = 1.0 / (2.0 * pulse_duration)
    sequence: list = [SetPoint(setpoint=2.6, rabi_up=rabi, rabi_down=rabi)]

    # 1. Velocity selection (always first).
    sequence.append(pi(Beam.UP, m=0, label="velsel"))
    sequence.append(Clearout(label="velsel-blast"))

    # 2. Optional pre-launch splitter -> two clouds, same velocity, separated.
    if do_split and n_split > 0:
        # pi/2 forks (e, 1) into an upper arm (g, 2) and a lower arm (e, 1).
        sequence.append(pi2(Beam.DOWN, m=1, label="split"))
        # Accelerate the upper arm, let it drift, accelerate the lower arm by
        # the same number of rungs (they stay one recoil / one flip apart), then
        # reconverge them onto one momentum class.
        sequence += ladder(start_m=2, n=n_split, first_beam=Beam.UP)
        sequence.append(Wait(t=_DARK_TIME_PLACEHOLDER, label="separate"))
        sequence += ladder(start_m=1, n=n_split, first_beam=Beam.DOWN)
        _append_recombine(sequence)

    # 3. Optional launch: accelerate the cloud(s) up together.
    state, m_now = _top_pair(sequence)
    if do_launch and n_launch > 0:
        first_beam = Beam.UP if state == GROUND else Beam.DOWN
        sequence += ladder(start_m=m_now, n=n_launch, first_beam=first_beam)
        state, m_now = _top_pair(sequence)

    # Optional zero-duration phase step just before the interferometer, to
    # exercise the applet's phase marker.
    if do_phase:
        sequence.append(Phase(phase=0.25, label="demo"))

    # 4. Interferometer (always): an n_lmt-recoil Mach-Zehnder on the pair.
    _append_interferometer(
        sequence, state=state, m=m_now, n_lmt=n_lmt, symmetric=symmetric
    )

    return sequence


def _events_from_compiled(compiled, *, pulse_duration, interrogation_time):
    """Lay synthetic timing over the compiled events to make an intent record.

    Pulses and clearouts each occupy ``pulse_duration`` / a short clearout time;
    Wait events record a dark-time intent row of ``interrogation_time``; set
    points are instantaneous and, unlike waits, are not part of the recorded
    intent stream.
    """
    clearout_duration = 5e-6
    events = []
    t = 0.0
    for ce in compiled.events:
        if ce.kind == EVENT_PULSE:
            events.append(
                _pulse(
                    t,
                    pulse_duration,
                    ce.state_effect,
                    ce.addressed_state,
                    ce.addressed_m,
                    ce.delta_m,
                )
            )
            t += pulse_duration
        elif ce.kind == EVENT_CLEAROUT:
            events.append(_clearout(t, clearout_duration))
            t += clearout_duration
        elif ce.kind == EVENT_CALLBACK:
            # A callback flattens to one ordinary pulse intent row per declared
            # action (addressed_state, addressed_m, delta_m, state_effect), all
            # sharing one t_start - exactly as register_intent_action records it.
            for (
                addressed_state,
                addressed_m,
                delta_m,
                state_effect,
            ) in ce.callback_actions:
                events.append(
                    _pulse(
                        t,
                        pulse_duration,
                        state_effect,
                        addressed_state,
                        addressed_m,
                        delta_m,
                    )
                )
            t += pulse_duration
        elif ce.kind == EVENT_PHASE:
            # Zero-duration marker: drawn by the applet, ignored by the walk.
            events.append(_phase(t))
        elif ce.kind == EVENT_WAIT:
            events.append(_wait(t, interrogation_time))
            t += interrogation_time
        elif ce.kind == EVENT_SETPOINT:
            pass  # instantaneous; not an atom-affecting event
    return events


class TestTrajectoryApplet(EnvExperiment):
    """Launch the LMT trajectory applet against a synthetic intent record."""

    def build(self):
        self.setattr_argument("do_split", BooleanValue(default=False))
        self.do_split: bool

        self.setattr_argument(
            "n_split",
            NumberValue(default=4, precision=0, step=1, min=0, max=32, type="int"),
        )
        self.n_split: int

        self.setattr_argument("do_launch", BooleanValue(default=True))
        self.do_launch: bool

        self.setattr_argument(
            "n_launch",
            NumberValue(default=12, precision=0, step=1, min=0, max=64, type="int"),
        )
        self.n_launch: int

        # Interferometer: number of LMT recoils (n_lmt=1 is a normal MZ; 0 is an
        # error), and the LMT geometry.
        self.setattr_argument(
            "n_lmt",
            NumberValue(default=1, precision=0, step=1, min=1, max=20, type="int"),
        )
        self.n_lmt: int

        self.setattr_argument(
            "interferometer_type",
            EnumerationValue(["asymmetric", "symmetric"], default="asymmetric"),
        )
        self.interferometer_type: str

        self.setattr_argument(
            "pulse_duration",
            NumberValue(default=30e-6, precision=1, type="float", unit="us"),
        )
        self.pulse_duration: float

        self.setattr_argument(
            "interrogation_time",
            NumberValue(default=1e-3, precision=3, type="float", unit="ms"),
        )
        self.interrogation_time: float

        self.setattr_argument("do_phase", BooleanValue(default=False))
        self.do_phase: bool

        self.setattr_argument("include_gravity", BooleanValue(default=False))
        self.include_gravity: bool

        self.setattr_device("ccb")
        self.ccb: CCB

    def run(self):
        sequence = _build_sequence(
            do_split=self.do_split,
            n_split=int(self.n_split),
            do_launch=self.do_launch,
            n_launch=int(self.n_launch),
            n_lmt=int(self.n_lmt),
            symmetric=self.interferometer_type == "symmetric",
            pulse_duration=self.pulse_duration,
            do_phase=self.do_phase,
        )
        compiled = compile_sequence(sequence, initial_population=_INITIAL_POPULATION)
        events = _events_from_compiled(
            compiled,
            pulse_duration=self.pulse_duration,
            interrogation_time=self.interrogation_time,
        )
        record = _record_from_events(events)

        # Same broadcast dataset PulseDMARecording publishes; the applet
        # subscribes to it by name. archive=False matches the live recorder and
        # avoids ragged-array h5py issues.
        self.set_dataset("pulse_intent_record", [record], broadcast=True, archive=False)
        logger.info("Published synthetic intent record with %d events", len(events))

        cmd = (
            "${python} -m repository.lib.applets.lmt_trajectory_applet "
            "pulse_intent_record"
        )
        if self.include_gravity:
            cmd += " --include-gravity"
        self.ccb.issue("create_applet", "LMT trajectory (test)", cmd)
        logger.info("Issued create_applet for the LMT trajectory applet")
