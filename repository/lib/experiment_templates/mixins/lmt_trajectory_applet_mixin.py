"""
Mixin that opens the LMT spacetime-trajectory applet for an experiment.

Issues ``create_applet`` CCB commands pointing
:mod:`repository.lib.applets.lmt_trajectory_applet` at the broadcast
``pulse_intent_record`` dataset that
:class:`~repository.lib.fragments.pulse_recorder_and_tracker.PulseDMARecording`
publishes each shot. Mix it into any declarative-LMT experiment (it shares the
recorded intent stream, so there is nothing to configure) to get a live
space-time / momentum diagram of the most recent sequence in the dashboard.

Two applets are opened: one in the freely-falling frame the simulator uses,
and one in the lab frame with the ½gt² free-fall parabola drawn on top.
"""

from artiq.master.worker_impl import CCB

#: Broadcast dataset PulseDMARecording publishes the intent stream to; the
#: applet subscribes to it by name.
PULSE_INTENT_RECORD_DATASET = "pulse_intent_record"


class LMTTrajectoryAppletMixin:
    """Open the LMT trajectory applets against the recorded intent stream."""

    def build_fragment(self):
        super().build_fragment()
        self.setattr_device("ccb")
        self.ccb: CCB

    def host_setup(self):
        super().host_setup()
        base_cmd = (
            "${python} -m repository.lib.applets.lmt_trajectory_applet "
            f"{PULSE_INTENT_RECORD_DATASET}"
        )
        self.ccb.issue("create_applet", "LMT trajectory", base_cmd)
        self.ccb.issue(
            "create_applet",
            "LMT trajectory (gravity)",
            base_cmd + " --include-gravity",
        )
