"""
Minimal worked example of a declarative-LMT launch with the repumped readout.

Loads the dipole trap, velocity-slices a class into the excited clock state,
clears the unselected ground atoms, and launches the selected class n=2 recoils
up the momentum ladder. The launch ends excited (|e, 3>), so it is imaged via
the 679/707 repump - atoms in |e> are dark to 461 fast-kinetics imaging.

Runs with defaults, no submit overrides. For a clean readout on a real rig you
still tune the ROI anchor (trap_x_pixel / trap_y_pixel) and each pulse's
frequency offset (p0N_..._offset); those are calibrations, not needed to run.
"""


from repository.lib.utils import _Stub


class DemoDeclarativeLMT(_Stub):
    """
    A minimal declarative-LMT launch with the repumped fast-kinetics readout.
    """


class DemoDeclarativeLMTCallback(_Stub):
    """
    Demo of the new :class:`Callback` API firing a clock pulse by hand.

    After the velocity slice leaves the selected class in ``(EXCITED, 1)``, a
    :class:`Callback` declares the equivalent of a single normal up-beam pi
    pulse on that class and fires it through the RAW, UNTRACKED switch-DDS path
    in :meth:`lmt_sequence_callback_hook`.

    The action's intent (an up-beam pi transfer of the pair
    ``(GROUND, 0) <-> (EXCITED, 1)``) is registered by the engine via
    ``register_intent_action`` immediately before dispatch, so the predictor
    already has a faithful pulse intent row. Firing the pulse through the
    tracked wrappers (``fire_lmt_pulse`` / ``set_clock_up_dds``) would register
    a SECOND intent row for the same pulse and double-count it in the pulse
    recorder - hence the deliberate raw ``clock_up_dds.sw.on()/off()`` path.
    """
