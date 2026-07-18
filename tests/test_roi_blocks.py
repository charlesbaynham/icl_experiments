"""Geometry and reduction tests for the shared single-image ROI blocks.

Pure host-side: these are the free functions the camera configs delegate to, so
the ROI layout and the background subtraction can be checked without an ARTIQ
fixture.
"""

import numpy as np
import pytest

from repository.lib.experiment_templates.mixins.andor_imaging.lmt_compensated_normalised_imaging import (
    _fill_clamped_roi,
)
from repository.lib.experiment_templates.mixins.andor_imaging.roi_blocks import (
    background_corrected_counts,
)
from repository.lib.experiment_templates.mixins.andor_imaging.roi_blocks import (
    clamp_roi_in_place,
)
from repository.lib.experiment_templates.mixins.andor_imaging.roi_blocks import (
    collapse_roi_in_place,
)
from repository.lib.experiment_templates.mixins.andor_imaging.roi_blocks import (
    fill_signal_bg_roi_row,
)
from repository.lib.experiment_templates.mixins.andor_imaging.roi_blocks import (
    rois_intersect,
)
from repository.lib.experiment_templates.mixins.andor_imaging.single_image_normalised_fast_kinetics_base import (
    _background_correct_trap_block,
)


def _row(x0=100, y0=200, x1=128, y1=216, bg_width=50):
    roi_buffer = np.zeros((3, 4), dtype=np.int32)
    fill_signal_bg_roi_row(roi_buffer, 0, 1, 2, x0, y0, x1, y1, bg_width)
    return roi_buffer


# %% Row geometry


def test_row_places_backgrounds_flanking_the_signal():
    rois = _row(x0=100, y0=200, x1=128, y1=216, bg_width=50)

    assert np.array_equal(rois[0], np.array([100, 200, 128, 216]))
    assert np.array_equal(rois[1], np.array([50, 200, 100, 216]))
    assert np.array_equal(rois[2], np.array([128, 200, 178, 216]))


def test_backgrounds_share_the_signal_y_extent():
    """The area-scaled subtraction assumes the flanks sample the same rows.

    A background box silently taller than its signal once produced a non-zero
    total atom number out of empty frames (lab book 2026-04-20), so the shared
    y extent is a property of the layout rather than a convention callers keep.
    """
    rois = _row()
    for i in (1, 2):
        assert rois[i][1] == rois[0][1]
        assert rois[i][3] == rois[0][3]


def test_backgrounds_keep_signal_y_extent_after_x_clamping():
    rois = _row(x0=10, y0=200, x1=38, y1=216, bg_width=50)

    # The left flank runs off the left edge of the sensor.
    for i in range(3):
        clamp_roi_in_place(rois, i, 0, 0, 512, 400)

    for i in (1, 2):
        assert rois[i][1] == rois[0][1]
        assert rois[i][3] == rois[0][3]


def test_zero_bg_width_gives_degenerate_flanks():
    rois = _row(bg_width=0)

    assert rois[1][0] == rois[1][2]
    assert rois[2][0] == rois[2][2]


# %% Clamping


@pytest.mark.parametrize("centre_x", [-40, 0, 5, 180, 500, 512, 600])
@pytest.mark.parametrize("centre_y", [-30, 0, 8, 100, 199, 200, 260])
def test_clamp_matches_the_centre_based_clamp(centre_x, centre_y):
    """``clamp_roi_in_place`` must agree with the ROI clamp already in use.

    The dynamic readout builds boxes from corners (so a signal and its flanks
    can be clamped independently) while the two-ROI readout builds them from a
    centre. Both must clip identically, or the two readouts would disagree about
    where a port near the frame edge actually sat.
    """
    half_width = 14
    half_height = 8
    frame_width = 512
    frame_height = 200

    reference = np.zeros((1, 4), dtype=np.int32)
    reference_clipped = _fill_clamped_roi(
        reference,
        0,
        centre_x,
        centre_y,
        half_width,
        half_height,
        frame_width,
        frame_height,
    )

    corners = np.zeros((1, 4), dtype=np.int32)
    corners[0][0] = centre_x - half_width
    corners[0][1] = centre_y - half_height
    corners[0][2] = centre_x + half_width
    corners[0][3] = centre_y + half_height
    clipped = clamp_roi_in_place(corners, 0, 0, 0, frame_width, frame_height)

    assert np.array_equal(corners[0], reference[0])
    assert clipped == reference_clipped


def test_clamp_reports_no_clipping_when_fully_inside():
    rois = _row(x0=100, y0=20, x1=128, y1=36, bg_width=50)

    assert clamp_roi_in_place(rois, 0, 0, 0, 512, 200) == 0


def test_fully_outside_roi_collapses_rather_than_inverting():
    rois = np.zeros((1, 4), dtype=np.int32)
    rois[0] = np.array([600, 300, 700, 340])

    assert clamp_roi_in_place(rois, 0, 0, 0, 512, 200) == 1
    assert rois[0][2] >= rois[0][0]
    assert rois[0][3] >= rois[0][1]


def test_collapse_zeroes_area_at_the_roi_origin():
    rois = _row()
    collapse_roi_in_place(rois, 1)

    assert rois[1][0] == rois[1][2]
    assert rois[1][1] == rois[1][3]


# %% Background reduction


def test_background_correction_matches_the_block_helper():
    areas = [60, 60, 30, 30, 30, 30]
    sums = [150, 90, 10, 20, 5, 10]

    ground, excited = _background_correct_trap_block(
        sums=sums, areas=areas, start_index=0
    )

    assert background_corrected_counts(sums, areas, 0, 2, 4) == ground
    assert background_corrected_counts(sums, areas, 1, 3, 5) == excited
    assert ground == pytest.approx(135.0)
    assert excited == pytest.approx(60.0)


def test_single_surviving_flank_still_normalises_by_area():
    """Retiring one flank must rescale by the survivor's area, not half of it."""
    areas = [60, 0, 30]
    sums = [150, 0, 10]

    # 150 - (60/30) * 10
    assert background_corrected_counts(sums, areas, 0, 1, 2) == pytest.approx(130.0)


def test_zero_background_area_returns_the_raw_signal():
    """Both flanks off-frame must not divide by zero on the kernel.

    Predicted ROIs can be driven off-frame, and a kernel-side ZeroDivisionError
    would kill the shot and the scan with it. The block helper picks the guard up
    too: the only inputs whose result changes are the ones that used to raise.
    """
    areas = [60, 0, 0]
    sums = [150, 0, 0]

    assert background_corrected_counts(sums, areas, 0, 1, 2) == pytest.approx(150.0)

    ground, excited = _background_correct_trap_block(
        sums=[150, 90, 0, 0, 0, 0], areas=[60, 60, 0, 0, 0, 0], start_index=0
    )
    assert ground == pytest.approx(150.0)
    assert excited == pytest.approx(90.0)


# %% Overlap detection


def test_touching_rois_do_not_count_as_intersecting():
    """A flank abuts its own signal by construction and must not read as overlap."""
    assert not rois_intersect(50, 200, 100, 216, 100, 200, 128, 216)


def test_separated_ports_do_not_intersect():
    assert not rois_intersect(166, 190, 194, 206, 166, 290, 194, 306)


def test_ports_nine_pixels_apart_intersect():
    """The 2026-06-21 failure: ports ~9 px apart, boxes 16 px tall.

    The excited box then integrates the ground cloud and the off-resonant
    baseline excitation reads ~0.10 instead of ~0.
    """
    assert rois_intersect(166, 190, 194, 206, 166, 199, 194, 215)


def test_intersection_is_symmetric():
    a = (166, 190, 194, 206)
    b = (180, 199, 208, 215)

    assert rois_intersect(*a, *b) == rois_intersect(*b, *a)
