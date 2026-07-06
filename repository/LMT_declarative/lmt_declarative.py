"""
LMT interferometry driven by the declarative sequence language.

This is the reference experiment for the declarative LMT stack
(:mod:`repository.lib.lmt_sequence` +
:class:`~repository.lib.experiment_templates.mixins.declarative_lmt.DeclarativeLMTBase`):
the velocity-selective pulse, the launch and a symmetric Mach-Zehnder
interferometer are declared as a single list of pulse descriptions, from
which scannable per-pulse parameters (detuning offsets and durations) are
generated with model-predicted defaults.
"""

from repository.lib.utils import Stub


class DeclarativeLMTSymmetricMachZehnder(Stub):
    """
    Declarative symmetric LMT interferometry
    """
