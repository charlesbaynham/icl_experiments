"""
Offline test harness for the LMT spacetime-trajectory applet.

Launches :mod:`repository.lib.applets.lmt_trajectory_applet` against a
hand-built ``pulse_intent_record`` so the applet can be exercised without any
hardware, kernel code or a live LMT shot.

The experiment is pure host code: it writes a synthetic interferometer intent
record to the broadcast ``pulse_intent_record`` dataset (the same format
:class:`~repository.lib.fragments.pulse_recorder_and_tracker.PulseDMARecording`
emits) and issues a ``create_applet`` CCB command pointing the applet at it. Run
it from the dashboard (or ``artiq_run``) on any machine with the ARTIQ master
running -- no core device is touched.

The synthetic sequence is an up-beam pi/2 - pi - pi/2 Mach-Zehnder on the
(g, 0) <-> (e, 1) pair, optionally followed by a ground-state clearout, which
exercises the applet's branch forking, solid/dotted state styling, shaded
pulses and clearout markers.
"""

import logging

from artiq.experiment import BooleanValue
from artiq.experiment import EnvExperiment
from artiq.experiment import NumberValue
from artiq.master.worker_impl import CCB

from repository.lib import pulse_intent as pi

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


def _pulse(t_start, duration, effect, state, m, delta_m):
    return {
        "kind": pi.Kind.PULSE,
        "t_start_s": t_start,
        "duration_s": duration,
        "state_effect": effect,
        "addressed_state": state,
        "addressed_m": m,
        "delta_m": delta_m,
    }


def _clearout(t_start, duration, state=pi.AddressedState.GROUND):
    return {
        "kind": pi.Kind.CLEAROUT,
        "t_start_s": t_start,
        "duration_s": duration,
        "state_effect": pi.StateEffect.NONE,
        "addressed_state": state,
        "addressed_m": pi.M_AUTO,
        "delta_m": 0,
    }


def _record_from_events(events):
    """Pack a list of event dicts into the 7-row float record the applet reads."""
    return [[float(e[key]) for e in events] for key in _RECORD_KEYS]


class TestTrajectoryApplet(EnvExperiment):
    """Launch the LMT trajectory applet against a synthetic intent record."""

    def build(self):
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

        self.setattr_argument("add_clearout", BooleanValue(default=True))
        self.add_clearout: bool

        self.setattr_device("ccb")
        self.ccb: CCB

    def run(self):
        t_pulse = self.pulse_duration
        T = self.interrogation_time

        # Up-beam pi/2 - pi - pi/2 Mach-Zehnder on the (g, 0) <-> (e, 1) pair.
        events = [
            _pulse(
                0.0, t_pulse, pi.StateEffect.SUPERPOSE, pi.AddressedState.GROUND, 0, +1
            ),
            _pulse(T, t_pulse, pi.StateEffect.FLIP, pi.AddressedState.GROUND, 0, +1),
            _pulse(
                2 * T,
                t_pulse,
                pi.StateEffect.SUPERPOSE,
                pi.AddressedState.GROUND,
                0,
                +1,
            ),
        ]
        if self.add_clearout:
            events.append(_clearout(2 * T + 2 * t_pulse, 5e-6))

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
        self.ccb.issue("create_applet", "LMT trajectory (test)", cmd)
        logger.info("Issued create_applet for the LMT trajectory applet")
