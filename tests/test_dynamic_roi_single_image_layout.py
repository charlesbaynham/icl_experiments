"""Layout tests for the dynamic six-ROI single-image readout.

``get_rois`` is a method on a built fragment, so these reproduce its geometry at
free-function level: the arithmetic under test is the mapping from two predicted
port centres to six clamped ROIs, which does not need a camera.
"""

import numpy as np
import pytest

from repository.lib.experiment_templates.mixins.andor_imaging.lmt_compensated_single_image_imaging import (
    EXC_BG_LEFT_ROI,
)
from repository.lib.experiment_templates.mixins.andor_imaging.lmt_compensated_single_image_imaging import (
    EXC_BG_RIGHT_ROI,
)
from repository.lib.experiment_templates.mixins.andor_imaging.lmt_compensated_single_image_imaging import (
    EXC_SIGNAL_ROI,
)
from repository.lib.experiment_templates.mixins.andor_imaging.lmt_compensated_single_image_imaging import (
    GND_BG_LEFT_ROI,
)
from repository.lib.experiment_templates.mixins.andor_imaging.lmt_compensated_single_image_imaging import (
    GND_BG_RIGHT_ROI,
)
from repository.lib.experiment_templates.mixins.andor_imaging.lmt_compensated_single_image_imaging import (
    GND_SIGNAL_ROI,
)
from repository.lib.experiment_templates.mixins.andor_imaging.lmt_compensated_single_image_imaging import (
    LMTCompensatedSingleImageCameraConfig,
)
from repository.lib.experiment_templates.mixins.andor_imaging.lmt_compensated_single_image_imaging import (
    NUM_SINGLE_IMAGE_DYNAMIC_ROIS,
)
from repository.lib.experiment_templates.mixins.andor_imaging.roi_blocks import (
    clamp_roi_in_place,
)
from repository.lib.experiment_templates.mixins.andor_imaging.roi_blocks import (
    fill_signal_bg_roi_row,
)

FK_HEIGHT = 100
FK_OFFSET = 166
SENSOR_WIDTH = 512
HALF_WIDTH = 14
HALF_HEIGHT = 8
BG_WIDTH = 50


def _build_rois(gnd_x, gnd_y, exc_x, exc_y, bg_width=BG_WIDTH):
    """Reproduce LMTCompensatedSingleImageCameraConfig.get_rois geometry."""
    roi_buffer = np.zeros((NUM_SINGLE_IMAGE_DYNAMIC_ROIS, 4), dtype=np.int32)

    gnd_y_frame = gnd_y - FK_OFFSET
    exc_y_frame = exc_y - FK_OFFSET + FK_HEIGHT

    fill_signal_bg_roi_row(
        roi_buffer,
        GND_SIGNAL_ROI,
        GND_BG_LEFT_ROI,
        GND_BG_RIGHT_ROI,
        gnd_x - HALF_WIDTH,
        gnd_y_frame - HALF_HEIGHT,
        gnd_x + HALF_WIDTH,
        gnd_y_frame + HALF_HEIGHT,
        bg_width,
    )
    fill_signal_bg_roi_row(
        roi_buffer,
        EXC_SIGNAL_ROI,
        EXC_BG_LEFT_ROI,
        EXC_BG_RIGHT_ROI,
        exc_x - HALF_WIDTH,
        exc_y_frame - HALF_HEIGHT,
        exc_x + HALF_WIDTH,
        exc_y_frame + HALF_HEIGHT,
        bg_width,
    )

    mask = 0
    for i in range(NUM_SINGLE_IMAGE_DYNAMIC_ROIS):
        y_min = 0 if i % 2 == 0 else FK_HEIGHT
        y_max = FK_HEIGHT if i % 2 == 0 else 2 * FK_HEIGHT
        if clamp_roi_in_place(roi_buffer, i, 0, y_min, SENSOR_WIDTH, y_max) != 0:
            mask |= 1 << i
    return roi_buffer, mask


def test_config_declares_the_single_image_cycle_shape():
    """One fast-kinetics series, six ROIs: the whole point of the merge.

    Two grabber readouts would mean the second (temporal background) acquisition
    was still happening, and the reduction would run twice per shot.
    """
    cfg = LMTCompensatedSingleImageCameraConfig

    assert cfg.num_grabber_rois == 6
    assert cfg.num_grabber_readouts == 1
    assert cfg.num_andor_images == 2
    assert cfg.fast_kinetics_num_shots == 2


def test_roi_indices_match_the_static_single_image_layout():
    """Signal boxes at 0/1 and flanks at 2..5, interleaved ground/excited.

    The applet index sets and the host-side overlay seeding both index this
    layout positionally.
    """
    assert (GND_SIGNAL_ROI, EXC_SIGNAL_ROI) == (0, 1)
    assert (GND_BG_LEFT_ROI, EXC_BG_LEFT_ROI) == (2, 3)
    assert (GND_BG_RIGHT_ROI, EXC_BG_RIGHT_ROI) == (4, 5)


def test_each_row_stays_inside_its_own_subframe():
    """The two sub-frames are separate exposures stacked in one buffer.

    A box spilling across the boundary would integrate rows belonging to the
    other port's image without anything flagging it.
    """
    rois, _ = _build_rois(gnd_x=200, gnd_y=270, exc_x=205, exc_y=250)

    for i in (GND_SIGNAL_ROI, GND_BG_LEFT_ROI, GND_BG_RIGHT_ROI):
        assert rois[i][1] >= 0
        assert rois[i][3] <= FK_HEIGHT
    for i in (EXC_SIGNAL_ROI, EXC_BG_LEFT_ROI, EXC_BG_RIGHT_ROI):
        assert rois[i][1] >= FK_HEIGHT
        assert rois[i][3] <= 2 * FK_HEIGHT


def test_excited_row_carries_no_gravity_shift_of_its_own():
    """The predicted excited_y already contains all inter-shot motion.

    The static configs displace their second row by
    ``fast_kinetics_height - excited_shift``; applying that here as well would
    double-count the fall, which on a 16 px-tall box means missing the cloud.
    """
    gnd_y = 250
    exc_y = 250

    rois, _ = _build_rois(gnd_x=200, gnd_y=gnd_y, exc_x=200, exc_y=exc_y)

    # Equal predicted y => the two rows differ by exactly the sub-frame height.
    assert rois[EXC_SIGNAL_ROI][1] - rois[GND_SIGNAL_ROI][1] == FK_HEIGHT

    # And a port predicted 20 px lower moves by exactly 20 px, nothing else.
    moved, _ = _build_rois(gnd_x=200, gnd_y=gnd_y, exc_x=200, exc_y=exc_y + 20)
    assert moved[EXC_SIGNAL_ROI][1] - rois[EXC_SIGNAL_ROI][1] == 20


def test_clip_mask_identifies_which_roi_clipped():
    """A clipped signal box and a clipped background box mean different things.

    With six boxes, a single "something clipped" flag cannot tell you whether to
    distrust the atom number or the background estimate.
    """
    # Push the ground row hard against the left edge: its left flank clips, the
    # signal box does not.
    rois, mask = _build_rois(gnd_x=60, gnd_y=250, exc_x=200, exc_y=250)

    assert mask & (1 << GND_BG_LEFT_ROI)
    assert not mask & (1 << GND_SIGNAL_ROI)
    assert not mask & (1 << EXC_SIGNAL_ROI)
    assert rois[GND_BG_LEFT_ROI][0] == 0


def test_no_clipping_reports_an_empty_mask():
    _, mask = _build_rois(gnd_x=200, gnd_y=250, exc_x=200, exc_y=250)

    assert mask == 0


@pytest.mark.parametrize("bg_width", [0, 10, 50, 120])
def test_flanks_track_the_signal_box_for_any_width(bg_width):
    rois, _ = _build_rois(
        gnd_x=200, gnd_y=250, exc_x=200, exc_y=250, bg_width=bg_width
    )

    assert rois[GND_BG_LEFT_ROI][2] == rois[GND_SIGNAL_ROI][0]
    assert rois[GND_BG_RIGHT_ROI][0] == rois[GND_SIGNAL_ROI][2]
    for i in (GND_BG_LEFT_ROI, GND_BG_RIGHT_ROI):
        assert rois[i][1] == rois[GND_SIGNAL_ROI][1]
        assert rois[i][3] == rois[GND_SIGNAL_ROI][3]
