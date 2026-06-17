"""
LMT spacetime-trajectory inference
==================================

Pure host-side (no ARTIQ) physics for inferring the *intended* spacetime
trajectory of a large-momentum-transfer (LMT) clock pulse sequence and turning
the lab's recorded ``pulse_record`` into something that can be drawn.

This is a self-contained port of the trajectory-inference half of the
``lmt_sim`` simulation package
(https://github.com/charlesbaynham/LMT_sim_scratch), restricted to what an
applet needs: decode a recorded pulse sequence, build the
``Pulse``/``Freefall`` event list, and walk an ideal stationary on-axis atom
through it deciding -- for every pulse -- whether each cloud flips, drifts, or
splits from the Bordé Rabi transition probability.

It deliberately reuses the same closed-form Bordé 2x2 matrix elements
(``_calculate_interaction_constants``) and the light-shift bookkeeping as the
simulator, so the inferred trajectory matches ``compute_spacetime_trajectory``
in ``lmt_sim``. The two must be kept in lockstep; this is the consumer side of
the ``pulse_record`` format emitted by ``PulseDMARecording`` in
``repository.lib.fragments.pulse_recorder_and_tracker`` (see
``lmt_resonance.py`` for the existing precedent of porting ``lmt_sim`` physics
into this repo).

Conventions match the rest of the declarative LMT stack:

- ``+z`` is up; gravity accelerates in ``-z``.
- The UP beam propagates bottom-to-top, ``k`` along ``+z``; its kick is ``k=+1``.
- Momentum classes ``m`` are integer photon recoils relative to launch.
- All frequencies are in Hz (not angular).
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import scipy.constants as _const

from repository.lib import constants
from repository.lib.physics.lmt_resonance import RECOIL_FREQUENCY_HZ

# --- Physical constants (mapped onto this repo's canonical values) ----------

#: Atom mass and clock wavelength come from the single source of truth in
#: ``repository.lib.constants`` so this module tracks the configured isotope.
MASS_ATOM = constants.SR_ATOM_MASS_KG
TRANSITION_WAVELENGTH = constants.CLOCK_WAVELENGTH_M
K_WAVEVECTOR = 2 * np.pi / TRANSITION_WAVELENGTH

#: Velocity gained per photon recoil, ``hbar k / M`` (~6.6 mm/s for Sr-87).
RECOIL_VELOCITY = _const.hbar * K_WAVEVECTOR / MASS_ATOM

#: Gravity Doppler ramp of the clock laser, ``f_clock * g / c`` (Hz per second).
GRAVITY_DOPPLER_PER_SEC_HZ = constants.GRAVITY_DOPPLER_PER_SEC_CLOCK

#: Sentinels written by ``PulseDMARecording`` as length-1 records. Stored as
#: float64 and so compared with a tolerance, not for exact equality.
PULSE_RECORD_SAME_AS_LAST_SENTINEL = -1.0
PULSE_RECORD_DISABLED_SENTINEL = -2.0
_PULSE_RECORD_SENTINEL_TOL = 0.5


# --- Sequence event types ---------------------------------------------------


@dataclass(frozen=True)
class Pulse:
    """One laser pulse addressing the clock transition.

    ``k`` is the beam direction (+1 up, -1 down); ``detuning_hz`` is the laser
    detuning in the freely-falling frame; ``rabi_frequency`` the (square-pulse)
    Rabi frequency in Hz; ``duration`` in seconds. ``probe_shift_coefficient``
    folds the intensity-dependent light shift into the effective detuning.
    """

    k: int
    detuning_hz: float
    rabi_frequency: float
    duration: float
    label: str = "LMT"
    probe_shift_coefficient: float = 0.0

    def __post_init__(self):
        if self.k not in (-1, +1):
            raise ValueError("Pulse k must be either +1 or -1")
        if self.rabi_frequency <= 0.0:
            raise ValueError("Pulse rabi_frequency must be positive")
        if self.duration < 0.0:
            raise ValueError("Pulse duration must be non-negative")


@dataclass(frozen=True)
class Freefall:
    duration: float
    label: str = "freefall"

    def __post_init__(self):
        if self.duration < 0.0:
            raise ValueError("Freefall duration must be non-negative")


@dataclass(frozen=True)
class Clearout:
    duration: float
    label: str = "clearout"

    def __post_init__(self):
        if self.duration < 0.0:
            raise ValueError("Clearout duration must be non-negative")


# --- Bordé 2x2 transition probability (closed form, no expm) ----------------


def _effective_detuning_hz(detuning_hz, probe_shift_coefficient, rabi_freq):
    """Laser detuning corrected for the intensity-dependent probe (light) shift.

    The shift scales with intensity (``rabi_freq**2``) and is subtracted because
    the recorded detuning sits above the bare resonance by this amount.
    """
    return detuning_hz - probe_shift_coefficient * rabi_freq**2


def _borde_omega_3(detuning_hz, k_sign, m_ground, vz=0.0):
    """Bordé recoil-shifted on-diagonal detuning (Eq. 7), angular units."""
    Delta = 2 * np.pi * detuning_hz
    delta_recoil = _const.hbar * K_WAVEVECTOR**2 / (2 * MASS_ATOM)
    return (
        Delta
        - k_sign * K_WAVEVECTOR * vz
        - ((m_ground + k_sign) ** 2 - m_ground**2) * delta_recoil
    )


def _transition_probability(m, is_ground, pulse: Pulse):
    """Rabi transition probability for a stationary on-axis atom at class ``m``.

    "Stationary" means the ``m=0`` state is stationary. Reuses the Bordé 2x2
    off-diagonal element ``B`` so the inferred trajectory matches the simulator;
    the probe (light) shift is folded into the effective detuning.
    """
    k = pulse.k
    m_ground = m if is_ground else m - k
    omega_ab = np.pi * pulse.rabi_frequency
    effective_detuning = _effective_detuning_hz(
        pulse.detuning_hz, pulse.probe_shift_coefficient, pulse.rabi_frequency
    )
    Omega_3 = _borde_omega_3(effective_detuning, k_sign=k, m_ground=m_ground)
    Omega = np.sqrt(Omega_3**2 + 4 * omega_ab**2)
    # Eq. 13: B = 2i * omega_ab / Omega * sin(Omega t / 2)
    B = 2j * omega_ab / Omega * np.sin(Omega * pulse.duration / 2)
    return float(abs(B) ** 2)


def _addressed_momentum_classes(pulse: Pulse):
    """Stationary on-axis ground/excited momentum classes addressed by ``pulse``.

    Uses the same effective detuning and ``vz=0`` convention as
    ``_transition_probability`` so the overlay matches the trajectory heuristic.
    """
    effective_detuning_hz = _effective_detuning_hz(
        pulse.detuning_hz, pulse.probe_shift_coefficient, pulse.rabi_frequency
    )
    m_ground = (effective_detuning_hz - RECOIL_FREQUENCY_HZ) / (
        2 * pulse.k * RECOIL_FREQUENCY_HZ
    )
    m_excited = m_ground + pulse.k
    return float(m_ground), float(m_excited)


# --- Build a sequence from a decoded lab pulse record -----------------------


def build_sequence_from_lab_pulse_dump(
    is_up,
    start_times_s,
    durations_s,
    opll_hz,
    switch_hz,
    delivery_hz,
    delivery_setpoint,
    probe_induced_alpha_up=1.8153e-05,
    probe_induced_alpha_down=1.8153e-05,
    pi_pulse_threshold_s=50e-6,
    initial_velocity_z=0.0,
):
    """Parse one shot's recorded pulse arrays into a ``Pulse``/``Freefall`` list.

    Ported verbatim (physics-wise) from ``lmt_sim.lmt_sequence``: it anchors the
    laser frequency on the first pulse (assumed a velocity-selection pi pulse
    that drives ``m=0 -> m=+-1``), compensates out the gravity Doppler ramp into
    the freely-falling frame, and folds the light shift into each pulse's
    ``probe_shift_coefficient``.

    Returns ``(timestamps, sequence)`` where ``timestamps`` are the absolute
    start times of each event (s) and ``sequence`` is the event list.
    """
    if pi_pulse_threshold_s <= 0.0:
        raise ValueError("pi_pulse_threshold_s must be positive")

    is_up_input = np.asarray(is_up)
    if is_up_input.dtype != bool and not np.all(np.isin(is_up_input, (0, 1))):
        raise ValueError("is_up must be a boolean array (or contain only 0/1)")
    is_up = is_up_input.astype(bool)
    start_times_s = np.asarray(start_times_s, dtype=float)
    durations_s = np.asarray(durations_s, dtype=float)
    opll_hz = np.asarray(opll_hz, dtype=float)
    switch_hz = np.asarray(switch_hz, dtype=float)
    delivery_hz = np.asarray(delivery_hz, dtype=float)
    delivery_setpoint = np.asarray(delivery_setpoint, dtype=float)

    lengths = {
        len(is_up),
        len(start_times_s),
        len(durations_s),
        len(opll_hz),
        len(switch_hz),
        len(delivery_hz),
        len(delivery_setpoint),
    }
    if len(lengths) != 1:
        raise ValueError("Lab pulse dump arrays must all have the same length")
    if len(is_up) == 0:
        return np.array([]), []

    timestamps = start_times_s
    durations = durations_s

    # The OPLL offsets the Sirah from the ECDL and we lock to the negative side;
    # the delivery and switch AOMs all use the -1st order. This "total laser
    # frequency" is defined in the lab rest frame.
    total_laser_frequency_hz = -opll_hz - switch_hz - delivery_hz
    # The overall offset is arbitrary, so normalise to the first pulse.
    total_laser_frequency_hz -= total_laser_frequency_hz[0]

    beam_sign = np.where(is_up, +1.0, -1.0)

    # Doppler shift each beam sees from the atom's velocity, evaluated at the
    # pulse CENTRE (the lab tunes for resonance there, not at the start).
    pulse_centre_times = timestamps + durations / 2
    up_beam_doppler_hz = (
        -initial_velocity_z / TRANSITION_WAVELENGTH
        + GRAVITY_DOPPLER_PER_SEC_HZ * pulse_centre_times
    )

    # Assume the first pulse is on resonance.
    rabi_freq_first_pulse = (
        1 / (2 * durations[0])
        if durations[0] > pi_pulse_threshold_s
        else 1 / (4 * durations[0])
    )
    first_pulse_probe_shift_hz = (
        probe_induced_alpha_up if is_up[0] else probe_induced_alpha_down
    ) * rabi_freq_first_pulse**2
    first_pulse_doppler_shift_hz = up_beam_doppler_hz[0] * beam_sign[0]
    # A velocity-selection pulse on a stationary atom is resonant one recoil
    # frequency ABOVE the bare transition for BOTH beam directions.
    first_pulse_atom_frame_detuning_hz = RECOIL_FREQUENCY_HZ

    centre_freq_hz = (
        total_laser_frequency_hz[0]
        + first_pulse_doppler_shift_hz
        - first_pulse_atom_frame_detuning_hz
        - first_pulse_probe_shift_hz
    )

    # Detuning of every beam in the freely-falling frame (gravity Doppler folded
    # in). The UP beam has k=+1, so gravity blue-shifts it.
    effective_laser_detuning_hz = (total_laser_frequency_hz - centre_freq_hz) + (
        up_beam_doppler_hz * beam_sign
    )

    sequence_timestamps = []
    sequence = []
    t_now = 0.0

    for (
        this_is_up,
        this_timestamp,
        this_duration,
        this_effective_laser_detuning_hz,
    ) in zip(is_up, timestamps, durations, effective_laser_detuning_hz):
        if this_timestamp < t_now:
            raise ValueError(
                f"Pulse timestamps must be non-decreasing. Got "
                f"{this_timestamp} < {t_now}."
            )
        if this_timestamp > t_now:
            sequence_timestamps.append(t_now)
            sequence.append(Freefall(duration=this_timestamp - t_now))
            t_now = this_timestamp

        if this_duration > pi_pulse_threshold_s:
            rabi_freq_hz = 1 / (2 * this_duration)
        else:
            rabi_freq_hz = 1 / (4 * this_duration)

        sequence_timestamps.append(this_timestamp)
        sequence.append(
            Pulse(
                k=+1 if this_is_up else -1,
                detuning_hz=this_effective_laser_detuning_hz,
                label="LMT",
                rabi_frequency=rabi_freq_hz,
                duration=this_duration,
                probe_shift_coefficient=(
                    probe_induced_alpha_up if this_is_up else probe_induced_alpha_down
                ),
            )
        )
        t_now += this_duration

    return np.array(sequence_timestamps), sequence


# --- Inferred-trajectory clouds ---------------------------------------------


@dataclass
class Cloud:
    """One branch of the inferred wavefunction.

    ``times``/``z``/``m``/``is_ground`` are per-event histories; ``alive`` is
    cleared when a clearout removes the branch; ``fork_index`` records where the
    branch split off its parent and ``color_index`` keys its colour.
    """

    times: list
    z: list
    m: list
    is_ground: list
    labels: list
    alive: bool = True
    fork_index: int = 0
    color_index: int = 0

    @property
    def v(self):
        return self.m[-1] * RECOIL_VELOCITY

    def _fork(self):
        return Cloud(
            times=list(self.times),
            z=list(self.z),
            m=list(self.m),
            is_ground=list(self.is_ground),
            labels=list(self.labels),
            fork_index=self.fork_index,
            color_index=self.color_index,
        )


def compute_spacetime_trajectory(sequence, *, flip_threshold=0.75, max_branches=None):
    """Infer the intended spacetime trajectory by simulating an ideal atom.

    Walks ``sequence`` with a stationary, on-axis, ground-state atom and decides
    for each pulse whether each cloud flips (``p >= flip_threshold``), drifts
    (``p <= 1 - flip_threshold``), or splits (in between), from the Rabi
    transition probability.

    Returns ``(clouds, clearout_times)``.
    """
    for event in sequence:
        if not isinstance(event, (Pulse, Clearout, Freefall)):
            raise TypeError(f"Unsupported sequence event type: {type(event)!r}")
    if max_branches is not None and max_branches < 1:
        raise ValueError("max_branches must be positive or None")

    t = 0.0
    clouds = [Cloud(times=[0.0], z=[0.0], m=[0], is_ground=[True], labels=[""])]
    clearout_times = []
    next_color_index = 1

    def enforce_max_branches():
        if max_branches is None:
            return
        live = sum(cloud.alive for cloud in clouds)
        if live > max_branches:
            raise RuntimeError(
                "compute_spacetime_trajectory exceeded max_branches: "
                f"{live} live branches > {max_branches}"
            )

    for event in sequence:
        dt = event.duration

        if isinstance(event, (Freefall, Clearout)):
            t += dt
            for cloud in clouds:
                if cloud.alive:
                    cloud.times.append(t)
                    cloud.z.append(cloud.z[-1] + cloud.v * dt)
                    cloud.m.append(cloud.m[-1])
                    cloud.is_ground.append(cloud.is_ground[-1])
                    cloud.labels.append(event.label)
            if isinstance(event, Clearout):
                clearout_times.append(t)
                for cloud in clouds:
                    if cloud.alive and cloud.is_ground[-1]:
                        cloud.alive = False
            continue

        # Pulse
        t += dt
        new_clouds = []
        for cloud in clouds:
            if not cloud.alive:
                new_clouds.append(cloud)
                continue
            p = _transition_probability(cloud.m[-1], cloud.is_ground[-1], event)
            if p >= flip_threshold:
                dm = event.k if cloud.is_ground[-1] else -event.k
                new_m = cloud.m[-1] + dm
                cloud.times.append(t)
                cloud.z.append(cloud.z[-1] + new_m * RECOIL_VELOCITY * dt)
                cloud.m.append(new_m)
                cloud.is_ground.append(not cloud.is_ground[-1])
                cloud.labels.append(event.label)
                new_clouds.append(cloud)
            elif p <= 1.0 - flip_threshold:
                cloud.times.append(t)
                cloud.z.append(cloud.z[-1] + cloud.v * dt)
                cloud.m.append(cloud.m[-1])
                cloud.is_ground.append(cloud.is_ground[-1])
                cloud.labels.append(event.label)
                new_clouds.append(cloud)
            else:
                drifter = cloud._fork()
                flipper = cloud._fork()
                flipper.fork_index = len(cloud.times)
                flipper.color_index = next_color_index
                next_color_index += 1
                drifter.times.append(t)
                drifter.z.append(drifter.z[-1] + drifter.v * dt)
                drifter.m.append(drifter.m[-1])
                drifter.is_ground.append(drifter.is_ground[-1])
                drifter.labels.append(event.label)
                dm = event.k if flipper.is_ground[-1] else -event.k
                new_m = flipper.m[-1] + dm
                flipper.times.append(t)
                flipper.z.append(flipper.z[-1] + new_m * RECOIL_VELOCITY * dt)
                flipper.m.append(new_m)
                flipper.is_ground.append(not flipper.is_ground[-1])
                flipper.labels.append(event.label)
                new_clouds.extend([drifter, flipper])
        clouds = new_clouds
        enforce_max_branches()

    return clouds, np.asarray(clearout_times)


def build_plot_trace(sequence, cloud):
    """Build the midpoint-convention drawing trace for one cloud.

    Mirrors ``_plot_spacetime.build_plot_trace`` from ``lmt_sim``: a pulse is
    drawn as two z-segments (drift to the pulse centre, then drift out at the new
    momentum) and the momentum as a vertical step at the pulse centre. The trace
    is sliced to start one event before the cloud's fork so branches only appear
    from their split point.

    Returns ``(times, positions, m_times, m, ground, m_ground)`` as arrays, all
    in SI units (seconds, metres, integer recoils).
    """
    times = [cloud.times[0]]
    positions = [cloud.z[0]]
    momentum_times = [cloud.times[0]]
    momentum = [cloud.m[0]]
    ground = [cloud.is_ground[0]]
    m_ground = [cloud.is_ground[0]]

    current_time = cloud.times[0]
    current_position = cloud.z[0]
    current_m = cloud.m[0]
    current_ground = cloud.is_ground[0]

    for i in range(len(cloud.times) - 1):
        event = sequence[i]
        dt = event.duration
        event_end_time = current_time + dt

        if isinstance(event, Pulse):
            mid_time = current_time + dt / 2
            mid_position = current_position + current_m * RECOIL_VELOCITY * dt / 2
            next_m = cloud.m[i + 1]
            next_ground = cloud.is_ground[i + 1]
            end_position = mid_position + next_m * RECOIL_VELOCITY * dt / 2

            times.extend([mid_time, event_end_time])
            positions.extend([mid_position, end_position])
            momentum_times.extend([mid_time, mid_time, event_end_time])
            momentum.extend([current_m, next_m, next_m])
            ground.extend([current_ground, next_ground])
            m_ground.extend([current_ground, next_ground, next_ground])
        else:
            next_m = cloud.m[i + 1]
            next_ground = cloud.is_ground[i + 1]
            end_position = current_position + current_m * RECOIL_VELOCITY * dt

            times.append(event_end_time)
            positions.append(end_position)
            momentum_times.append(event_end_time)
            momentum.append(next_m)
            ground.append(next_ground)
            m_ground.append(next_ground)

        current_time = event_end_time
        current_position = positions[-1]
        current_m = momentum[-1]
        current_ground = ground[-1]

    fi = max(0, cloud.fork_index - 1)
    z_start = sum(2 if isinstance(sequence[i], Pulse) else 1 for i in range(fi))
    m_start = sum(3 if isinstance(sequence[i], Pulse) else 1 for i in range(fi))

    return (
        np.asarray(times[z_start:]),
        np.asarray(positions[z_start:]),
        np.asarray(momentum_times[m_start:]),
        np.asarray(momentum[m_start:]),
        np.asarray(ground[z_start:], dtype=bool),
        np.asarray(m_ground[m_start:], dtype=bool),
    )


# --- Decode the broadcast ``pulse_record`` dataset --------------------------


def _is_sentinel(record, sentinel):
    return (
        len(record) == 1
        and len(record[0]) == 1
        and abs(float(record[0][0]) - sentinel) < _PULSE_RECORD_SENTINEL_TOL
    )


def most_recent_valid_record(records):
    """Return the most recently *stored* 7-row record from ``pulse_record``.

    ``records`` is the live broadcast ``pulse_record`` dataset: a list whose
    entries are either a genuine record (7 rows of ``num_pulses`` floats:
    directions, start times, durations, opll, switch, delivery, setpoint) or a
    length-1 sentinel (``[[-1.0]]`` "same as last", ``[[-2.0]]`` "disabled").

    Scanning from the end, the first genuine record is returned -- a trailing
    "same as last" sentinel just re-uses it, and "disabled" shots stored nothing.
    Returns ``None`` if no genuine record exists yet.
    """
    for record in reversed(list(records)):
        if len(record) == 7 and not _is_sentinel(
            record, PULSE_RECORD_SAME_AS_LAST_SENTINEL
        ):
            return [np.asarray(row, dtype=float) for row in record]
    return None


def infer_trajectory_from_pulse_record(records, **build_kwargs):
    """Lightweight end-to-end inference from a recorded ``pulse_record``.

    Picks the most recent valid sequence, builds the event list and infers the
    spacetime trajectory. Returns ``(sequence, clouds, clearout_times)``, or
    ``None`` if no valid sequence has been recorded yet.
    """
    record = most_recent_valid_record(records)
    if record is None:
        return None
    (
        directions,
        start_times_s,
        durations_s,
        opll_hz,
        switch_hz,
        delivery_hz,
        delivery_setpoint,
    ) = record
    if len(directions) == 0:
        return None
    _timestamps, sequence = build_sequence_from_lab_pulse_dump(
        is_up=directions,
        start_times_s=start_times_s,
        durations_s=durations_s,
        opll_hz=opll_hz,
        switch_hz=switch_hz,
        delivery_hz=delivery_hz,
        delivery_setpoint=delivery_setpoint,
        **build_kwargs,
    )
    clouds, clearout_times = compute_spacetime_trajectory(sequence)
    return sequence, clouds, clearout_times


#: matplotlib tab10 palette as RGB tuples, so the applet's colours match the
#: simulator's matplotlib figure exactly.
TAB10_RGB = [
    (31, 119, 180),
    (255, 127, 14),
    (44, 160, 44),
    (214, 39, 40),
    (148, 103, 189),
    (140, 86, 75),
    (227, 119, 194),
    (127, 127, 127),
    (188, 189, 34),
    (23, 190, 207),
]
