"""
Mixin that opens the LMT spacetime-trajectory applet for an experiment.

Issues a ``create_applet`` CCB command pointing
:mod:`repository.lib.applets.lmt_trajectory_applet` at the broadcast
``pulse_intent_record`` dataset that
:class:`~repository.lib.fragments.pulse_recorder_and_tracker.PulseDMARecording`
publishes each shot. Mix it into any declarative-LMT experiment (it shares the
recorded intent stream, so there is nothing to configure) to get a live
space-time / momentum diagram of the most recent sequence in the dashboard.

Set ``lmt_trajectory_applet_include_gravity = True`` on the experiment class to
draw the lab-frame free-fall parabola instead of the freely-falling frame.
"""

from artiq.master.worker_impl import CCB

#: Broadcast dataset PulseDMARecording publishes the intent stream to; the
#: applet subscribes to it by name.
PULSE_INTENT_RECORD_DATASET = "pulse_intent_record"


class LMTTrajectoryAppletMixin:
    """Open the LMT trajectory applet against the recorded intent stream."""

    #: Draw the ½gt² free-fall parabola (lab frame) rather than the
    #: freely-falling frame the simulator uses.
    lmt_trajectory_applet_include_gravity: bool = False

    def build_fragment(self):
        super().build_fragment()
        self.setattr_device("ccb")
        self.ccb: CCB

    def host_setup(self):
        super().host_setup()
        cmd = (
            "${python} -m repository.lib.applets.lmt_trajectory_applet "
            f"{PULSE_INTENT_RECORD_DATASET}"
        )
        if self.lmt_trajectory_applet_include_gravity:
            cmd += " --include-gravity"
        self.ccb.issue("create_applet", "LMT trajectory", cmd)
