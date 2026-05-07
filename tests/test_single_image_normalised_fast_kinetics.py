import numpy as np

from repository.lib.experiment_templates.mixins.andor_imaging import (
    single_image_normalised_fast_kinetics as single_image_fk,
)
from repository.lib.experiment_templates.mixins.andor_imaging.single_image_normalised_fast_kinetics_base import (
    _background_correct_trap_block,
)
from repository.lib.experiment_templates.mixins.andor_imaging.single_image_normalised_fast_kinetics_base import (
    _single_trap_roi_block,
)


def test_single_trap_roi_block_builds_ground_excited_and_background_rois():
    rois = _single_trap_roi_block(
        x0=100,
        y0=200,
        x1=120,
        y1=230,
        offset=7,
        step=40,
        bg_width=8,
    )

    assert np.array_equal(
        rois,
        np.array(
            [
                [100, 193, 120, 223],
                [100, 233, 120, 263],
                [92, 193, 100, 223],
                [92, 233, 100, 263],
                [120, 193, 128, 223],
                [120, 233, 128, 263],
            ],
            dtype=np.int32,
        ),
    )


def test_background_correct_trap_block_scales_background_by_roi_area():
    areas = np.array([60, 60, 30, 30, 30, 30], dtype=np.int32)
    sums = np.array([150, 90, 10, 20, 5, 10], dtype=np.int32)

    ground_atom_number, excited_atom_number = _background_correct_trap_block(
        sums=sums,
        areas=areas,
        start_index=0,
    )

    assert ground_atom_number == 135.0
    assert excited_atom_number == 60.0


def test_public_module_exposes_concrete_single_image_mixins():
    assert hasattr(
        single_image_fk, "SingleImageNormalisedSingleTrapRepumpedSpectroscopyMixin"
    )
    assert hasattr(
        single_image_fk,
        "SingleImageNormalisedSingleTrapClockPulseSpectroscopyMixin",
    )
    assert hasattr(
        single_image_fk,
        "SingleImageNormalisedDoubleTrapRepumpedInterferometryMixin",
    )
    assert hasattr(
        single_image_fk,
        "SingleImageNormalisedDoubleTrapClockPulseInterferometryMixin",
    )
