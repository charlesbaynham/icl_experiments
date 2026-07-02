"""Host-side tests for the dynamic-ROI camera config helpers."""

import numpy as np
import pytest

from repository.lib import constants
from repository.lib.experiment_templates.mixins.andor_imaging.lmt_compensated_normalised_imaging import (
    LMTCompensatedCameraConfig,
)
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


# ── Fast-kinetics readout-window offset ───────────────────────────────────────


@pytest.fixture
def cfg(fragment_factory):
    """A built LMTCompensatedCameraConfig with params initialised to defaults."""
    return fragment_factory(LMTCompensatedCameraConfig)


def _set(handle, value):
    handle._store.set_value(value)


def test_default_offset_is_the_constant_and_both_consumers_agree(cfg):
    # Auto off (default): the hardware accessor and get_rois() must read the
    # same manual param, and it must default to the constant -> zero behaviour
    # change vs the pre-param code.
    assert cfg.fast_kinetics_offset_auto.get() is False
    assert cfg.fast_kinetics_offset_setpoint.get() == constants.ANDOR_FAST_KINETICS_OFFSET
    assert cfg.get_fast_kinetics_offset() == constants.ANDOR_FAST_KINETICS_OFFSET
    assert cfg._current_fk_offset() == cfg.fast_kinetics_offset_setpoint.get()


def test_get_rois_offset_matches_manual_param_when_auto_off(cfg):
    cfg.host_setup()  # seeds gnd/excited to the trap centre
    offset = 123
    _set(cfg.fast_kinetics_offset_setpoint, offset)

    rois = cfg.get_rois()
    # ROI 0 (ground) frame-y = gnd_y - offset; centred, so its y-centre is
    # gnd_y - offset. Recover the offset the config actually used.
    half_height = cfg.roi_height.get() // 2
    gnd_y_frame_centre = rois[0][1] + half_height
    assert cfg.gnd_y - gnd_y_frame_centre == offset


def test_offset_param_max_keeps_frame_on_sensor(cfg):
    # The param's max and _max_fk_offset both encode offset + num_shots*height
    # <= sensor height, the same constraint setup_fast_kinetics_mode enforces.
    expected_max = (
        constants.ANDOR_SENSOR_HEIGHT
        - cfg.fast_kinetics_num_shots * cfg.fast_kinetics_height
    )
    assert cfg._max_fk_offset == expected_max
    assert (
        cfg._max_fk_offset + cfg.fast_kinetics_num_shots * cfg.fast_kinetics_height
        == constants.ANDOR_SENSOR_HEIGHT
    )


def test_auto_offset_centres_window_on_predicted_ground_row(cfg):
    _set(cfg.fast_kinetics_offset_auto, True)
    cfg.gnd_y = 260

    offset = cfg.update_auto_offset()
    assert offset == 260 - cfg.fast_kinetics_height // 2
    # In auto mode both consumers read the freshly-derived value.
    assert cfg._current_fk_offset() == offset
    assert cfg.get_fast_kinetics_offset() == offset


def test_auto_offset_is_clamped_to_sensor(cfg):
    _set(cfg.fast_kinetics_offset_auto, True)

    cfg.gnd_y = -50
    assert cfg.update_auto_offset() == 0

    cfg.gnd_y = constants.ANDOR_SENSOR_HEIGHT + 100
    assert cfg.update_auto_offset() == cfg._max_fk_offset


def test_auto_off_ignores_auto_value_and_uses_manual_param(cfg):
    # With auto off, a stale _auto_offset must never leak into the readout.
    cfg._auto_offset = 999
    _set(cfg.fast_kinetics_offset_setpoint, 77)
    assert cfg.fast_kinetics_offset_auto.get() is False
    assert cfg._current_fk_offset() == 77
    assert cfg.get_fast_kinetics_offset() == 77
