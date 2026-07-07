"""Base class for auto-generated experiment stubs.

This is the only hand-written module on the stubs branch. ``_Stub`` is a
minimal ARTIQ experiment whose name starts with an underscore so the
explorer never lists it directly; every generated stub subclasses it.
"""

from artiq.experiment import EnvExperiment


class _Stub(EnvExperiment):
    def build(self):
        pass

    def run(self):
        raise NotImplementedError("Stub")
