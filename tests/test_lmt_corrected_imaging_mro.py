"""Regression tests for the dynamic-ROI imaging hook resolution.

``NormalisedFastKineticsLMTCorrectedMixin`` mixes the clock pi pulse of
``NormalisedFastKineticsClockPulseMixin`` with the trajectory-driven ROIs of
``DynamicROIImagingMixin``. Both branches descend from
``NormalisedFastKineticsBase`` (which provides a *static* config and the default
imaging hook), so the contract is delicate: the dynamic mixin must win
``get_andor_camera_config_hook`` and ``do_imaging_hook_andor`` (otherwise the
camera gets a config with no ``calculate_atom_positions`` and the ROIs never
track the cloud), while the clock mixin must still win ``do_first_pulse`` (the
pi pulse that brings the excited population down before imaging).

These tests pin that resolution both at the mixin level (cheap, MRO only) and at
the level of the two concrete declarative-LMT experiments (full fragment build).
"""

from repository.lib.experiment_templates.mixins.andor_imaging.lmt_compensated_normalised_imaging import (
    DynamicROIImagingMixin,
)
from repository.lib.experiment_templates.mixins.andor_imaging.lmt_compensated_normalised_imaging import (
    LMTCompensatedCameraConfig,
)
from repository.lib.experiment_templates.mixins.andor_imaging.lmt_compensated_normalised_imaging import (
    NormalisedFastKineticsLMTCorrectedMixin,
)
from repository.lib.experiment_templates.mixins.andor_imaging.normalised_fast_kinetics_base import (
    NormalisedFastKineticsClockPulseMixin,
)


def _provider(cls, method_name):
    """The class in ``cls.__mro__`` whose ``__dict__`` defines ``method_name``."""
    for base in cls.__mro__:
        if method_name in base.__dict__:
            return base
    raise AssertionError(f"{method_name} not found in MRO of {cls.__name__}")


def test_mixin_resolves_dynamic_roi_hooks():
    cls = NormalisedFastKineticsLMTCorrectedMixin

    assert (
        _provider(cls, "get_andor_camera_config_hook") is DynamicROIImagingMixin
    ), "Dynamic ROI config hook must win over the static base config"
    assert (
        _provider(cls, "do_imaging_hook_andor") is DynamicROIImagingMixin
    ), "Dynamic ROI imaging hook must win over the static base imaging hook"

    # The clock pi pulse must still win - it is the whole point of pairing with
    # NormalisedFastKineticsClockPulseMixin.
    assert (
        _provider(cls, "do_first_pulse") is NormalisedFastKineticsClockPulseMixin
    ), "Clock pi-pulse must still provide do_first_pulse"


def test_declarative_lmt_builds_dynamic_roi_config(fragment_factory):
    from repository.LMT.lmt_declarative import DeclarativeLMTSymmetricMachZehnderFrag

    frag = fragment_factory(DeclarativeLMTSymmetricMachZehnderFrag)
    assert isinstance(frag.andor_camera_config, LMTCompensatedCameraConfig)


def test_declarative_lmt_global_builds_dynamic_roi_config(fragment_factory):
    from repository.LMT.lmt_declarative_global import (
        DeclarativeLMTGlobalSymmetricMachZehnderFrag,
    )

    frag = fragment_factory(DeclarativeLMTGlobalSymmetricMachZehnderFrag)
    assert isinstance(frag.andor_camera_config, LMTCompensatedCameraConfig)
