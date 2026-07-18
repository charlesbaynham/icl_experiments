"""
Numerical-equivalence tests for moving the dynamic-ROI prediction off the
real-time timeline into ``before_start_hook``.

The refactor changed *where* and *with what inputs* the predictor is called, not
the position maths: the inline imaging-hook path fed live-timeline image
timestamps plus ``(t_playback_start_mu, t_release_mu)``; the new
``before_start_hook`` path feeds chosen times of flight (seconds since release)
plus the recording-relative offset ``t_release_mu - t_playback_start_mu``.

These tests prove the two input constructions produce identical predicted pixel
positions, using the same building blocks as
``LMTCompensatedCameraConfig._calculate_positions_host``
(:func:`repository.lib.physics.trajectory.predict_port_pixels`). They are pure
Python/NumPy - no ARTIQ fixtures.
"""

import numpy as np
import pytest
import scipy.constants

from repository.lib.physics import lmt_resonance as pulse_intent
from repository.lib.physics.ballistic import BallisticConfig
from repository.lib.physics.ballistic import CameraGeometry
from repository.lib.physics.trajectory import live_times_to_seconds_since_release
from repository.lib.physics.trajectory import predict_port_pixels
from repository.lib.physics.trajectory import rebase_record_times_mu

# ── Geometry (side-view camera, as in test_ballistic_predictor) ────────────────

PIXEL_SIZE_M = 16e-6
MAGNIFICATION = 1.0
CENTRE_PIXEL = (256.0, 256.0)
SR87_MASS_KG = scipy.constants.atomic_mass * 87
CLOCK_WAVELENGTH_M = scipy.constants.c / 429_228_004_229_872.99
GRAVITY = scipy.constants.g

CFG = BallisticConfig(
    mass_kg=SR87_MASS_KG,
    gravity_vec_m_per_s2=np.array([0.0, 0.0, -GRAVITY]),
    clock_beam_direction=np.array([0.0, 0.0, 1.0]),
    clock_wavelength_m=CLOCK_WAVELENGTH_M,
    camera=CameraGeometry(
        optical_axis=np.array([0.0, 1.0, 0.0]),
        sensor_x_axis=np.array([1.0, 0.0, 0.0]),
        sensor_y_axis=np.array([0.0, 0.0, 1.0]),
        centre_pixel=CENTRE_PIXEL,
        pixel_size_m=PIXEL_SIZE_M,
        magnification=MAGNIFICATION,
    ),
)

REF_PERIOD_S = 1e-9


def _predict_pixels(t_start_s, duration_s, intent, t_image_ground_s, t_image_excited_s):
    """Mirror ``_calculate_positions_host``: build events, predict, round.

    Returns ``(gnd_x, gnd_y, exc_x, exc_y, gnd_mult, exc_mult)`` as ints.
    """
    events = pulse_intent.intent_events_from_arrays(
        t_start_s=t_start_s,
        duration_s=duration_s,
        kinds=intent["kinds"],
        state_effects=intent["state_effects"],
        addressed_states=intent["addressed_states"],
        addressed_m=intent["addressed_m"],
        delta_m=intent["delta_m"],
    )
    out = predict_port_pixels(
        events,
        t_image_ground_s=t_image_ground_s,
        t_image_excited_s=t_image_excited_s,
        cfg=CFG,
    )
    gnd = out["ground"]
    exc = out["excited"]
    return (
        int(round(gnd.x_pixel)),
        int(round(gnd.y_pixel)),
        int(round(exc.x_pixel)),
        int(round(exc.y_pixel)),
        gnd.multiplicity,
        exc.multiplicity,
    )


# A representative recorded sequence: velocity-slice (up pi), clearout, then a
# two-pulse launch ladder. Recording-relative start times / durations in mu.
_SLICED_LAUNCH = dict(
    start_times_mu=np.array([200_000, 600_000, 1_000_000, 1_200_000], dtype=np.int64),
    durations_mu=np.array([380_000, 50_000, 55_000, 55_000], dtype=np.int64),
    intent=dict(
        kinds=[
            int(pulse_intent.Kind.PULSE),
            int(pulse_intent.Kind.CLEAROUT),
            int(pulse_intent.Kind.PULSE),
            int(pulse_intent.Kind.PULSE),
        ],
        state_effects=[
            int(pulse_intent.StateEffect.FLIP),
            int(pulse_intent.StateEffect.NONE),
            int(pulse_intent.StateEffect.FLIP),
            int(pulse_intent.StateEffect.FLIP),
        ],
        addressed_states=[
            int(pulse_intent.AddressedState.AUTO),
            int(pulse_intent.AddressedState.GROUND),
            int(pulse_intent.AddressedState.EXCITED),
            int(pulse_intent.AddressedState.GROUND),
        ],
        addressed_m=[
            pulse_intent.M_AUTO,
            pulse_intent.M_AUTO,
            1,
            2,
        ],
        delta_m=[1, 0, 1, 1],
    ),
)

_EMPTY = dict(
    start_times_mu=np.array([], dtype=np.int64),
    durations_mu=np.array([], dtype=np.int64),
    intent=dict(
        kinds=[],
        state_effects=[],
        addressed_states=[],
        addressed_m=[],
        delta_m=[],
    ),
)


@pytest.mark.parametrize(
    "seq", [_SLICED_LAUNCH, _EMPTY], ids=["sliced_launch", "empty"]
)
@pytest.mark.parametrize(
    "t_playback_mu,t_release_mu",
    [
        # Dipole-like: release follows playback origin (offset = +t_dipole_beams_off).
        (5_000_000, 5_100_000),
        # Red-MOT-like: release precedes playback (offset = -expansion_time).
        (5_000_000, 4_000_000),
    ],
    ids=["release_after_playback", "release_before_playback"],
)
def test_recording_relative_matches_live_timestamps(seq, t_playback_mu, t_release_mu):
    """Old (live-timestamp) and new (TOF + offset) inputs give identical pixels."""
    image_tof_s = 2e-3
    image_tof_excited_s = image_tof_s + 1.5e-3

    starts = seq["start_times_mu"]
    duration_s = seq["durations_mu"].astype(np.int64) * REF_PERIOD_S

    # OLD inline path: image times are live timestamps; event times rebased with
    # the absolute playback + release cursors.
    t1_mu = int(t_release_mu + round(image_tof_s / REF_PERIOD_S))
    t2_mu = int(t_release_mu + round(image_tof_excited_s / REF_PERIOD_S))
    t_start_old = rebase_record_times_mu(
        starts, t_playback_mu, t_release_mu, REF_PERIOD_S
    )
    t_image_old = live_times_to_seconds_since_release(
        [t1_mu, t2_mu], t_release_mu, REF_PERIOD_S
    )
    old = _predict_pixels(
        t_start_old,
        duration_s,
        seq["intent"],
        float(t_image_old[0]),
        float(t_image_old[1]),
    )

    # NEW before_start_hook path: image times are the chosen TOFs directly;
    # event times rebased with a zero playback origin and the recording-relative
    # offset (t_release - t_playback).
    offset_mu = t_release_mu - t_playback_mu
    t_start_new = rebase_record_times_mu(starts, 0, offset_mu, REF_PERIOD_S)
    new = _predict_pixels(
        t_start_new,
        duration_s,
        seq["intent"],
        image_tof_s,
        image_tof_excited_s,
    )

    assert old == new


def test_rebase_identity():
    """The relocation rests on rebase(t, p, r) == rebase(t, 0, r - p)."""
    starts = np.array([200_000, 600_000, 1_000_000], dtype=np.int64)
    t_playback_mu, t_release_mu = 5_000_000, 5_100_000
    direct = rebase_record_times_mu(starts, t_playback_mu, t_release_mu, REF_PERIOD_S)
    offset = rebase_record_times_mu(
        starts, 0, t_release_mu - t_playback_mu, REF_PERIOD_S
    )
    assert np.allclose(direct, offset)
