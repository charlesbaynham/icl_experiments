"""
Shared ROI-block geometry and background reduction for the single-image
readouts.

Both the static single-image configs (positions baked from
:mod:`repository.lib.constants`) and the dynamic LMT-compensated one (positions
predicted per shot from the pulse-intent stream) lay out the same unit: a
*signal* ROI with a background ROI flanking it on either side, all three sharing
one y extent, reduced by area-scaled subtraction. Only the origin of the centre
differs, so the geometry and the reduction live here as ``@portable`` free
functions rather than being duplicated per config.

These allocate nothing: the caller owns an ``(N, 4)`` int32 buffer, because
``@portable`` code cannot safely allocate and return a fresh NumPy array.
"""

from artiq.language import TBool
from artiq.language import TFloat
from artiq.language import TInt32
from artiq.language import portable


@portable
def fill_signal_bg_roi_row(
    roi_buffer,
    signal_index,
    bg_left_index,
    bg_right_index,
    x0,
    y0,
    x1,
    y1,
    bg_width,
):
    """Write one signal ROI plus its two flanking background ROIs.

    The backgrounds abut the signal horizontally (``bg_width`` wide each) and
    take the signal's y extent verbatim. The shared y is the point of this
    function: the area-scaled subtraction in :func:`background_corrected_counts`
    assumes the flanks sample the same rows as the signal, and a background box
    silently 25 px taller than its signal once produced a non-zero total atom
    number out of empty frames (lab book 2026-04-20).
    """
    roi_buffer[signal_index][0] = x0
    roi_buffer[signal_index][1] = y0
    roi_buffer[signal_index][2] = x1
    roi_buffer[signal_index][3] = y1

    roi_buffer[bg_left_index][0] = x0 - bg_width
    roi_buffer[bg_left_index][1] = y0
    roi_buffer[bg_left_index][2] = x0
    roi_buffer[bg_left_index][3] = y1

    roi_buffer[bg_right_index][0] = x1
    roi_buffer[bg_right_index][1] = y0
    roi_buffer[bg_right_index][2] = x1 + bg_width
    roi_buffer[bg_right_index][3] = y1


@portable
def clamp_roi_in_place(
    roi_buffer, index, x_min, y_min, x_max, y_max
) -> TInt32:  # pyright: ignore[reportInvalidTypeForm]
    """Clamp ROI ``index`` into the given bounds, returning 1 if it moved.

    Ordering is re-enforced afterwards (``x1 >= x0``, ``y1 >= y0``) so an ROI
    driven entirely outside the bounds collapses to zero area rather than going
    negative. Zero area is a defined state downstream:
    :func:`background_corrected_counts` treats a zero-area background as absent
    instead of dividing by it.
    """
    x0 = roi_buffer[index][0]
    y0 = roi_buffer[index][1]
    x1 = roi_buffer[index][2]
    y1 = roi_buffer[index][3]

    cx0 = min(max(x0, x_min), x_max)
    cy0 = min(max(y0, y_min), y_max)
    cx1 = min(max(x1, x_min), x_max)
    cy1 = min(max(y1, y_min), y_max)

    clipped = 0
    if cx0 != x0 or cy0 != y0 or cx1 != x1 or cy1 != y1:
        clipped = 1

    roi_buffer[index][0] = cx0
    roi_buffer[index][1] = cy0
    roi_buffer[index][2] = max(cx1, cx0)
    roi_buffer[index][3] = max(cy1, cy0)
    return clipped


@portable
def collapse_roi_in_place(roi_buffer, index):
    """Collapse ROI ``index`` to zero area, in place, at its own origin.

    Used to retire a background ROI that has drifted onto the other port's
    signal: a zero-area background contributes neither counts nor area, so
    :func:`background_corrected_counts` falls back to the surviving flank
    without needing to be told which one it lost.
    """
    roi_buffer[index][2] = roi_buffer[index][0]
    roi_buffer[index][3] = roi_buffer[index][1]


@portable
def background_corrected_counts(
    sums, areas, signal_index, bg_a_index, bg_b_index
) -> TFloat:  # pyright: ignore[reportInvalidTypeForm]
    """Signal counts less its area-scaled flanking background.

    The two backgrounds are pooled and rescaled to the signal ROI's area, so an
    asymmetrically clipped or retired flank still normalises correctly. If both
    have zero area the raw signal sum is returned uncorrected: predicted ROIs
    can be driven off-frame, and a kernel-side division by zero would kill the
    shot and the scan with it. The caller's clip mask records the condition.
    """
    background_area = areas[bg_a_index] + areas[bg_b_index]
    if background_area == 0:
        return float(sums[signal_index])

    norm_factor = areas[signal_index] / background_area
    return sums[signal_index] - norm_factor * (sums[bg_a_index] + sums[bg_b_index])


@portable
def rois_intersect(
    ax0: TInt32,  # pyright: ignore[reportInvalidTypeForm]
    ay0: TInt32,  # pyright: ignore[reportInvalidTypeForm]
    ax1: TInt32,  # pyright: ignore[reportInvalidTypeForm]
    ay1: TInt32,  # pyright: ignore[reportInvalidTypeForm]
    bx0: TInt32,  # pyright: ignore[reportInvalidTypeForm]
    by0: TInt32,  # pyright: ignore[reportInvalidTypeForm]
    bx1: TInt32,  # pyright: ignore[reportInvalidTypeForm]
    by1: TInt32,  # pyright: ignore[reportInvalidTypeForm]
) -> TBool:  # pyright: ignore[reportInvalidTypeForm]
    """Whether two axis-aligned ROIs share any area.

    Touching edges do not count as intersecting, matching how the flanks are
    built: a background ROI abuts its own signal at ``x0``/``x1`` by
    construction and must not be read as overlapping it.

    Written as separate rejections rather than a chained ``and`` because ARTIQ
    types ``and`` by its operands, so the chained form infers as int, not bool.
    """
    if ax0 >= bx1:
        return False
    if bx0 >= ax1:
        return False
    if ay0 >= by1:
        return False
    if by0 >= ay1:
        return False
    return True
