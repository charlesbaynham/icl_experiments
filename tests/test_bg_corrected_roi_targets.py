import numpy as np

from repository.lib.experiment_templates.mixins.andor_imaging.imaging_base import (
    AndorImagingBase,
)

split = AndorImagingBase._split_bg_corrected_roi_targets


def test_split_single_trap_ground_is_roi0_excited_is_roi1_shifted():
    rois = np.array(
        [
            [100, 200, 120, 230],  # ground signal
            [100, 260, 120, 290],  # excited signal (one fk_height lower in frame)
        ],
        dtype=np.int32,
    )
    fk_height = 50

    ground, excited = split(rois, fk_height)

    assert ground == [[100, 200, 120, 230]]
    # Excited ROI mapped back into the excited sub-frame: y shifted up by fk_height
    assert excited == [[100, 210, 120, 240]]


def test_split_double_trap_uses_index_pairs():
    rois = np.array(
        [
            [10, 100, 20, 130],  # trap-A ground
            [10, 200, 20, 230],  # trap-A excited
            [30, 100, 40, 130],  # trap-B ground
            [30, 200, 40, 230],  # trap-B excited
        ],
        dtype=np.int32,
    )
    fk_height = 70

    ground, excited = split(
        rois, fk_height, ground_indices=(0, 2), excited_indices=(1, 3)
    )

    assert ground == [[10, 100, 20, 130], [30, 100, 40, 130]]
    assert excited == [[10, 130, 20, 160], [30, 130, 40, 160]]
