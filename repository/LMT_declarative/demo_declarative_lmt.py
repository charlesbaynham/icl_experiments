"""AUTO-GENERATED stub file - do not edit by hand.

Regenerate with ``scripts/generate_stubs.py``. Every class here mirrors
the name and docstring of a real experiment on a source branch; the
body is a no-op stub so the ARTIQ explorer can list it without any of
the real dependencies.
"""

from repository.stub_experiment import _Stub


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
