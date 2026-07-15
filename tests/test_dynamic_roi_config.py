"""Host-side tests for the dynamic-ROI camera config helpers."""

import numpy as np

from repository.lib.experiment_templates.mixins.andor_imaging.lmt_compensated_normalised_imaging import (
    _fill_clamped_roi,
)

FRAME_WIDTH = 512
FRAME_HEIGHT = 80  # 2 * fast_kinetics_height for a 40-row subarea


def _make_buffer():
    return np.zeros((2, 4), dtype=np.int32)


def test_in_frame_roi_is_unclamped():
    buf = _make_buffer()
    clipped = _fill_clamped_roi(buf, 0, 100, 40, 25, 10, FRAME_WIDTH, FRAME_HEIGHT)
    assert clipped == 0
    assert list(buf[0]) == [75, 30, 125, 50]


def test_roi_clamps_to_frame_edges_and_reports_it():
    buf = _make_buffer()
    # Centre near the top-left corner: x0 and y0 fall below zero
    clipped = _fill_clamped_roi(buf, 0, 10, 5, 25, 10, FRAME_WIDTH, FRAME_HEIGHT)
    assert clipped == 1
    assert list(buf[0]) == [0, 0, 35, 15]

    # Centre near the bottom-right corner: x1 and y1 exceed the frame
    clipped = _fill_clamped_roi(buf, 1, 505, 78, 25, 10, FRAME_WIDTH, FRAME_HEIGHT)
    assert clipped == 1
    assert list(buf[1]) == [480, 68, FRAME_WIDTH, FRAME_HEIGHT]


def test_fully_off_frame_roi_is_degenerate_but_valid():
    buf = _make_buffer()
    # Entirely below the frame (e.g. the cloud fell out of the readout area)
    clipped = _fill_clamped_roi(buf, 0, 100, 500, 25, 10, FRAME_WIDTH, FRAME_HEIGHT)
    assert clipped == 1
    x0, y0, x1, y1 = buf[0]
    assert x1 >= x0
    assert y1 >= y0
    assert (x1 - x0) * (y1 - y0) >= 0
    assert list(buf[0]) == [75, FRAME_HEIGHT, 125, FRAME_HEIGHT]

    # Entirely to the left of the frame
    clipped = _fill_clamped_roi(buf, 1, -200, 40, 25, 10, FRAME_WIDTH, FRAME_HEIGHT)
    assert clipped == 1
    x0, y0, x1, y1 = buf[1]
    assert x1 >= x0
    assert y1 >= y0
    assert list(buf[1]) == [0, 30, 0, 50]


def test_zero_size_roi_at_exact_frame_corner_is_not_clamped():
    buf = _make_buffer()
    clipped = _fill_clamped_roi(buf, 0, 0, 0, 0, 0, FRAME_WIDTH, FRAME_HEIGHT)
    assert clipped == 0
    assert list(buf[0]) == [0, 0, 0, 0]
