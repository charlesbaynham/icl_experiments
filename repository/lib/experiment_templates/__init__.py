"""
This module provides a set of generic experiments which should be subclassed for
particular uses, and can be customized by using "mixins" which override "hooks".
See the documentation for :class:`~.RedMOTWithExperiment` for more information.

TODO: Write proper documentation for the mixin / generic experiment stuff.
"""

from .dipole_trap_experiment import DipoleTrapWithExperiment
from .red_mot_experiment import RedMOTWithExperiment

__all__ = ["RedMOTWithExperiment", "DipoleTrapWithExperiment"]
