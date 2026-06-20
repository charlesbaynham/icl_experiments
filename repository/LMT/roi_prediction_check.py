"""
Dynamic-ROI position-predictor validation on the declarative-LMT stack.

This is a *diagnostic* experiment whose only purpose is to check that the
intent-driven cloud-position predictor in
:class:`~repository.lib.experiment_templates.mixins.andor_imaging.lmt_compensated_normalised_imaging.NormalisedFastKineticsLMTCorrectedMixin`
places the camera ROIs onto the atoms once gravity and the imparted momentum
are accounted for, and to confirm the axis/sign conventions that confused the
overnight ROI work.

Three conditions are built, each scanning a wait time ``flight_time`` between
the (optional) momentum kick and imaging:

* ``RoiCheckFall``  - no kick: pure free fall under gravity.
* ``RoiCheckUp``    - a clock-recoil ladder ending at momentum class ``+N``:
  the cloud should rise (and slowly fall back).
* ``RoiCheckDown``  - a ladder ending at momentum class ``-N``: the cloud
  should fall faster than free fall.

Each variant reuses the *exact* dipole stack, dynamic-ROI imaging mixin and
EMGain mixin of
:class:`~repository.LMT.lmt_declarative.DeclarativeLMTMachZehnderFrag`, so the
predictor under test is the production one.

Momentum-class convention (verified with ``compile_sequence`` in the build
tests, and traced through the physics):

* :class:`~repository.lib.lmt_sequence.Beam.UP` has sign ``+1``,
  :class:`~repository.lib.lmt_sequence.Beam.DOWN` has sign ``-1``; a pi pulse
  takes ``|g, m> -> |e, m + sign>``.
* The trajectory model (:mod:`repository.lib.physics.trajectory`) gives a
  branch velocity ``m * v_recoil * clock_beam_direction`` with
  ``clock_beam_direction = +z`` and ``gravity = -z`` (see
  :mod:`repository.lib.constants`). So momentum class ``+N`` is genuinely
  *upward* and ``-N`` is *downward*.

The up ladder alternates UP, DOWN, UP, ... climbing ``m = 0, 1, 2, ...``; the
down ladder alternates DOWN, UP, DOWN, ... descending ``m = 0, -1, -2, ...``.
Both end with an even number of pulses, leaving a single clean ground-state
branch at ``+N`` / ``-N`` for imaging. (The stock ``ladder`` helper only walks
upward in ``m``, so the down ladder is built explicitly here.)
"""

from artiq.language import kernel
from ndscan.experiment.entry_point import make_fragment_scan_exp
from ndscan.experiment.parameters import FloatParam
from ndscan.experiment.parameters import FloatParamHandle

from repository.lib import constants
from repository.lib.experiment_templates.dipole_trap_experiment import (
    DipoleTrapWithExperimentBase,
)
from repository.lib.experiment_templates.mixins.andor_imaging.em_gain import EMGainMixin
from repository.lib.experiment_templates.mixins.andor_imaging.lmt_compensated_normalised_imaging import (
    NormalisedFastKineticsLMTCorrectedMixin,
)
from repository.lib.experiment_templates.mixins.declarative_lmt import (
    DeclarativeLMTBase,
)
from repository.lib.experiment_templates.mixins.evaporation_mixin import (
    FieldOnlyRampInEvapMixin,
)
from repository.lib.experiment_templates.mixins.optical_pumping import (
    OpticalPumpingWithFieldSettingDipoleTrapMixin,
)
from repository.lib.experiment_templates.mixins.XODT_loading import LoadSingleXODTMixin
from repository.lib.experiment_templates.mixins.XODT_molasses import (
    XODTSingleMolassesPlusDipoleRampMixin,
)
from repository.lib.lmt_sequence import Beam
from repository.lib.lmt_sequence import Clearout
from repository.lib.lmt_sequence import SetPoint
from repository.lib.lmt_sequence import Wait
from repository.lib.lmt_sequence import pi

CLOCK_BEAM_DELIVERY_INFO = constants.SUSERVOED_BEAMS["clock_delivery"]

# Number of recoils imparted in the UP/DOWN conditions. Sized so the three
# trajectories diverge clearly over the flight_time scan while the cloud stays
# within the short (~100 px, gravity) imaging axis: at v_recoil ~ 6.6 mm/s and
# 62500 px/m, N=20 over 0-4 ms gives up ~ +28 px, down ~ -38 px (gravity adds
# to the down recoil), free fall ~ -5 px. Even => a single clean ground branch.
N_RECOILS = 20

# Default wait scan range (seconds). Gravity alone moves the cloud only a few
# px over this window; the recoil drift dominates and is what diverges the
# three conditions.
FLIGHT_TIME_DEFAULT_S = 1e-3


def _up_ladder(n: int) -> list:
    """Alternating UP, DOWN, ... pulses climbing m = 0, 1, ..., n-1.

    Pulse ``j`` addresses momentum class ``j`` of the populated state; the
    population walks |g,0> -> |e,+1> -> |g,+2> -> ... ending at |g, +n> for
    even ``n``.
    """
    beams = (Beam.UP, Beam.DOWN)
    return [pi(beams[j % 2], m=j, label="launch") for j in range(n)]


def _down_ladder(n: int) -> list:
    """Alternating DOWN, UP, ... pulses descending m = 0, -1, ..., -(n-1).

    The mirror image of :func:`_up_ladder`: population walks
    |g,0> -> |e,-1> -> |g,-2> -> ... ending at |g, -n> for even ``n``.
    """
    beams = (Beam.DOWN, Beam.UP)
    return [pi(beams[j % 2], m=-j, label="launch") for j in range(n)]


def _full_intensity_setpoint() -> SetPoint:
    """The launch/imaging set point at full delivery intensity, declaring the
    Rabi frequencies that set the default pi-pulse durations."""
    return SetPoint(
        setpoint=CLOCK_BEAM_DELIVERY_INFO.setpoint,
        rabi_up=1 / (2 * constants.CLOCK_PI_TIME),
        rabi_down=1 / (2 * constants.DOWN_CLOCK_BEAM_PI_TIME),
    )


def _slice_setpoint() -> SetPoint:
    """The reduced-intensity, long velocity-selective "slice" set point.

    Replicates the production slice in
    :class:`~repository.LMT.lmt_declarative.DeclarativeLMTMachZehnderFrag`: a
    low delivery set point (``constants.CLOCK_SHELVING_PULSE_SETPOINT`` = 0.012
    V) giving a reduced up-beam Rabi, so the declared pi time is the long
    ``constants.CLOCK_SHELVING_PULSE_TIME`` (380 us). At ~1 uK this selects a
    narrow velocity class (~9.5 kHz line).
    """
    return SetPoint(
        setpoint=constants.CLOCK_SHELVING_PULSE_SETPOINT,
        rabi_up=1 / (2 * constants.CLOCK_SHELVING_PULSE_TIME),
        label="slice",
    )


def _build_roicheck_frag(sequence: list):
    """Build a ROI-check fragment class wrapping a declared ``lmt_sequence``.

    The class body (mixins, hooks, the reused scannable ``flight_time``
    FloatParam) is identical for every variant; only the declared
    ``lmt_sequence`` differs, so it is passed in.
    """

    class _RoiCheckFrag(
        DeclarativeLMTBase,
        # Repositions the camera ROIs along the ballistic trajectory predicted
        # from the recorded pulse sequence (the predictor under test). NB: do
        # not also mix in a static-config imaging mixin - it would win
        # get_andor_camera_config_hook and install a config without
        # calculate_atom_positions.
        NormalisedFastKineticsLMTCorrectedMixin,
        EMGainMixin,
        LoadSingleXODTMixin,
        XODTSingleMolassesPlusDipoleRampMixin,
        OpticalPumpingWithFieldSettingDipoleTrapMixin,
        FieldOnlyRampInEvapMixin,
        DipoleTrapWithExperimentBase,
    ):
        """ROI-predictor validation: release, optional kick, scanned wait."""

        # Released from the trap in the ground state with no kicks.
        lmt_initial_population = {("g", 0)}
        lmt_sequence = sequence

        def build_fragment(self):
            super().build_fragment()
            # Own scannable wait reused by the Wait(param="flight_time") event.
            self.setattr_param(
                "flight_time",
                FloatParam,
                "Dark time between the momentum kick and imaging",
                default=FLIGHT_TIME_DEFAULT_S,
                unit="ms",
                min=0.0,
            )
            self.flight_time: FloatParamHandle

        @kernel
        def DMA_initialization_hook(self):
            self.DMA_initialization_hook_redmot_default()
            self.DMA_initialization_hook_dipole_trap_default()
            self.DMA_initialization_hook_loading_xodt_mot()
            self.DMA_initialization_hook_xodt_molasses()
            self.DMA_initialization_hook_evap_with_field_ramp()

        @kernel
        def post_sequence_cleanup_hook(self):
            self.post_sequence_cleanup_hook_base()
            self.post_sequence_cleanup_hook_andor()
            self.post_sequence_cleanup_hook_declarative_lmt()

    return _RoiCheckFrag


def _make(sign: int, n: int):
    """Build one ROI-check fragment class.

    Args:
        sign: ``0`` for free fall (no kick), ``+1`` for an upward ladder to
            ``+n``, ``-1`` for a downward ladder to ``-n``.
        n: Number of recoils to impart (ignored when ``sign == 0``).
    """
    if sign == 0:
        kick: list = []
    elif sign > 0:
        kick = _up_ladder(n)
    else:
        kick = _down_ladder(n)

    sequence = [
        # Full delivery intensity for the launch (and so the imaging set point
        # is well defined). No reduced-intensity "slice" pulse is needed here:
        # this is a position diagnostic, not spectroscopy.
        _full_intensity_setpoint(),
        *kick,
        # Scannable dark time between the kick and imaging. Reuses the
        # fragment's own 'flight_time' FloatParam (resolved in host_setup) so
        # the scan axis has a clean, stable FQN: <class>.flight_time.
        Wait(param="flight_time", label="flight"),
    ]
    return _build_roicheck_frag(sequence)


def _make_sliced():
    """Build the velocity-SLICED 2-recoil ROI-check fragment class.

    Unlike :func:`_make` (which launches the whole thermal cloud straight from
    a full-Rabi ladder), this variant first applies a weak, long,
    velocity-selective "slice" pi pulse on m=0 at the reduced slice set point -
    replicating the production slice + clearout in
    :class:`~repository.LMT.lmt_declarative.DeclarativeLMTMachZehnderFrag`:

    1. ``SetPoint`` at the reduced slice set point (long pi time) -> the slice
       pi addresses only a narrow velocity class.
    2. ``pi(Beam.UP, m=0, label="slice")`` shelves that class |g,0> -> |e,+1>,
       imparting +1 recoil.
    3. ``SetPoint`` back to full delivery intensity (so the launch pi and the
       imaging set point are well defined).
    4. ``Clearout()`` blasts away the un-sliced ground-state atoms (the
       declared population is already |e,+1>, so the compiler removes nothing;
       physically it removes the unselected ground cloud).
    5. ``pi(Beam.DOWN, m=1, label="launch")`` flips |e,+1> -> |g,+2>, adding a
       second recoil.

    The result is a clean, ground-state, imageable |g,+2> launch of a single
    narrow velocity class - a clean confirmation that 2 photon recoils were
    imparted.
    """
    sequence = [
        # Reduced-intensity, long velocity-selective slice set point.
        _slice_setpoint(),
        # Slice pi on m=0: shelves a narrow velocity class |g,0> -> |e,+1>.
        pi(Beam.UP, m=0, label="slice"),
        # Restore full delivery intensity for the launch and imaging set point.
        _full_intensity_setpoint(),
        # Blast away the un-sliced ground-state atoms (leaves |e,+1> only).
        Clearout(),
        # Full-Rabi launch pi: flips |e,+1> -> |g,+2> (the second recoil),
        # ending at the imageable ground state |g,+2>.
        pi(Beam.DOWN, m=1, label="launch"),
        # Scannable dark time between the launch and imaging. Reuses the
        # fragment's own 'flight_time' FloatParam so the scan axis has a clean,
        # stable FQN: <class>.flight_time.
        Wait(param="flight_time", label="flight"),
    ]
    return _build_roicheck_frag(sequence)


def _make_sliced_baseline():
    """Build the SLICED no-net-launch baseline ROI-check fragment class.

    The matched CONTROL for :func:`_make_sliced`. It is identical up to and
    including the slice + clearout, but the final pi *returns* the selected
    velocity class to the imageable ground state |g,0> with ZERO net momentum
    instead of launching it to |g,+2>:

    1. ``SetPoint`` at the reduced slice set point (long pi time).
    2. ``pi(Beam.UP, m=0, label="slice")`` shelves a narrow class
       |g,0> -> |e,+1> (+1 recoil).
    3. ``SetPoint`` back to full delivery intensity.
    4. ``Clearout()`` blasts away the un-sliced ground-state atoms (leaves
       |e,+1> only).
    5. ``pi(Beam.UP, m=1, label="return")`` flips |e,+1> -> |g,0>: addressing
       the EXCITED population at m=1 with the UP beam (sign +1) resolves the
       pair |g,0> <-> |e,+1>, so the pi de-shelves to |g,0>, *removing* the
       slice recoil rather than adding a second one. (Verified with
       ``compile_sequence``: the sign of the imparted recoil depends on which
       internal state is addressed - here UP returns, whereas DOWN would launch
       to |g,+2>.)

    The result is the SAME slice-selected velocity class and the SAME pulse
    count and sequence duration as the |g,+2> launch variant, but ending at
    rest (|g,0>). Differencing the two trajectories therefore isolates exactly
    the launch recoils, with the slice-selection velocity and the sequence
    duration cancelling between the two.
    """
    sequence = [
        # Reduced-intensity, long velocity-selective slice set point.
        _slice_setpoint(),
        # Slice pi on m=0: shelves a narrow velocity class |g,0> -> |e,+1>.
        pi(Beam.UP, m=0, label="slice"),
        # Restore full delivery intensity for the return pi and imaging set
        # point (matched, position for position, to the launch variant).
        _full_intensity_setpoint(),
        # Blast away the un-sliced ground-state atoms (leaves |e,+1> only).
        Clearout(),
        # Full-Rabi RETURN pi: de-shelves |e,+1> -> |g,0> (UP beam, addressing
        # the excited m=1 population), undoing the slice recoil so the cloud
        # ends at rest with zero net momentum - the no-net-launch baseline.
        pi(Beam.UP, m=1, label="return"),
        # Scannable dark time before imaging. Reuses the fragment's own
        # 'flight_time' FloatParam so the scan axis has a clean, stable FQN:
        # <class>.flight_time.
        Wait(param="flight_time", label="flight"),
    ]
    return _build_roicheck_frag(sequence)


def _sliced_launch_ladder(n: int) -> list:
    """The launch ladder fired AFTER the velocity slice + clearout.

    The slice (``pi(Beam.UP, m=0)``) has already shelved the selected class to
    ``|e,+1>``. This ladder then adds ``n`` further launch pi pulses, ONE LMT
    AT A TIME, never skipping a momentum class:

    * launch pulse 1: ``pi(Beam.DOWN, m=1)`` flips ``|e,+1> -> |g,+2>``,
    * launch pulse 2: ``pi(Beam.UP,   m=2)`` flips ``|g,+2> -> |e,+3>``,
    * launch pulse 3: ``pi(Beam.DOWN, m=3)`` flips ``|e,+3> -> |g,+4>``, ...

    i.e. launch pulse ``k`` (1-indexed) addresses momentum class ``k`` with the
    DOWN beam when ``k`` is odd and the UP beam when ``k`` is even, walking the
    single populated branch from ``|e,+1>`` to ``m = n + 1``. The end internal
    state is GROUND for odd ``n`` (``n+1`` even) and EXCITED for even ``n``.

    Args:
        n: Number of launch pi pulses after the slice (the first DOWN pulse is
            ``n == 1``). Must be ``>= 1``.
    """
    if n < 1:
        raise ValueError(f"sliced launch ladder needs n >= 1, got {n}")
    # k = 1, 2, ..., n addresses m = 1, 2, ..., n. Odd k -> DOWN, even k -> UP.
    beams = (Beam.DOWN, Beam.UP)
    return [pi(beams[(k - 1) % 2], m=k, label="launch") for k in range(1, n + 1)]


def _make_sliced_launch(n: int):
    """Build a velocity-SLICED launch-ladder ROI-check fragment with ``n``
    launch pulses fired one LMT at a time after the slice + clearout.

    Generalises :func:`_make_sliced` (which is the ``n == 1`` case): a weak,
    long, velocity-selective slice pi on m=0 shelves a narrow class
    ``|g,0> -> |e,+1>``, the un-sliced ground cloud is cleared out, then ``n``
    full-Rabi launch pi pulses climb the momentum ladder one recoil at a time
    (see :func:`_sliced_launch_ladder`). Built so a rig agent can scan the
    FINAL launch pulse's frequency offset at each ``n`` to confirm the cloud
    actually lands in the predicted class, building the launch up
    pulse-by-pulse without ever skipping an LMT.

    End state: ``|g, n+1>`` for odd ``n``, ``|e, n+1>`` for even ``n`` (always a
    single clean branch, so the ROI tracks one cloud).
    """
    sequence = [
        # Reduced-intensity, long velocity-selective slice set point.
        _slice_setpoint(),
        # Slice pi on m=0: shelves a narrow velocity class |g,0> -> |e,+1>.
        pi(Beam.UP, m=0, label="slice"),
        # Restore full delivery intensity for the launch and imaging set point.
        _full_intensity_setpoint(),
        # Blast away the un-sliced ground-state atoms (leaves |e,+1> only).
        Clearout(),
        # n launch pi pulses, fired one LMT at a time (never skipping a class).
        *_sliced_launch_ladder(n),
        # Scannable dark time before imaging. Reuses the fragment's own
        # 'flight_time' FloatParam so the scan axis has a clean, stable FQN:
        # <class>.flight_time.
        Wait(param="flight_time", label="flight"),
    ]
    return _build_roicheck_frag(sequence)


# -- Three variants: free fall, upward (+N), downward (-N) --------------------

RoiCheckFall = _make(sign=0, n=0)
RoiCheckFall.__name__ = "RoiCheckFall"
RoiCheckFall.__qualname__ = "RoiCheckFall"

RoiCheckUp = _make(sign=+1, n=N_RECOILS)
RoiCheckUp.__name__ = "RoiCheckUp"
RoiCheckUp.__qualname__ = "RoiCheckUp"

RoiCheckDown = _make(sign=-1, n=N_RECOILS)
RoiCheckDown.__name__ = "RoiCheckDown"
RoiCheckDown.__qualname__ = "RoiCheckDown"

# Small-N upward variants for gentle launches (n must stay even for a clean
# ground-state branch; n=2 is the minimal clean kick).
RoiCheckUp2 = _make(sign=+1, n=2)
RoiCheckUp2.__name__ = "RoiCheckUp2"
RoiCheckUp2.__qualname__ = "RoiCheckUp2"

RoiCheckUp8 = _make(sign=+1, n=8)
RoiCheckUp8.__name__ = "RoiCheckUp8"
RoiCheckUp8.__qualname__ = "RoiCheckUp8"

# Slice-LESS single-pulse spectroscopy pair (no slice, no clearout): release ->
# full-intensity set point -> ONE clock pi at offset (scanned) -> flight ->
# image. RoiCheckUp1 fires UP (|g,0> -> |e,+1>), RoiCheckDown1 fires DOWN
# (|g,0> -> |e,-1>); both end EXCITED, so on the ground-fluorescence readout the
# resonance is a depletion DIP. Because there is NO velocity slice, these pulses
# are NOT self-referenced, so the v0 Doppler term does NOT cancel: comparing the
# UP-first and DOWN-first residual resonance centres (with lmt_initial_velocity
# = 0 and switches nominal) is the clean discriminator between a genuine
# opposite-signed initial-velocity v0 (UP and DOWN shift antisymmetrically,
# R_up ~ -R_down) and a per-beam frequency-bookkeeping error (DOWN-specific
# R_down large, R_up ~ 0). The scan knob is the single pulse's offset:
# RoiCheckUp1.p01_pi_u_m0_launch_offset / RoiCheckDown1.p01_pi_d_m0_launch_offset.
RoiCheckUp1 = _make(sign=+1, n=1)
RoiCheckUp1.__name__ = "RoiCheckUp1"
RoiCheckUp1.__qualname__ = "RoiCheckUp1"

RoiCheckDown1 = _make(sign=-1, n=1)
RoiCheckDown1.__name__ = "RoiCheckDown1"
RoiCheckDown1.__qualname__ = "RoiCheckDown1"


def _make_up_prep_clearout_down():
    """Un-sliced excited-state DOWN-transition spectroscopy: tests whether the
    -20 kHz sliced-down-launch offset is a static |e>-addressed DOWN m_term
    bookkeeping error rather than a velocity slice artifact or a cloud v0.

    Sequence (NO velocity slice): full-intensity SetPoint -> full-Rabi UP pi on
    m=0 (|g,0> -> |e,+1>, prepares the excited population on the WHOLE cloud) ->
    Clearout (blast residual |g,0>, leaving |e,+1> dark) -> DOWN pi addressing
    the excited m=1 population (|e,+1> -> |g,+2>, scanned offset) -> flight ->
    image. Ends GROUND (|g,+2>), so on the ground-fluorescence readout the
    resonance is an APPEARANCE PEAK.

    This drives the EXACT same |e,+1> -> |g,+2> DOWN transition as the sliced
    launch in RoiCheckUp2Sliced, but WITHOUT the weak/long velocity slice, so it
    isolates the addressed-transition (m_term) offset from any slice-pulse
    effect. If the DOWN pi still peaks at ~ -20 kHz, the offset is a static
    excited-state DOWN m_term bookkeeping error; if it peaks at ~0, the slice was
    responsible. The scan knob is RoiCheckUp1ClrDown.p03_pi_d_m1_launch_offset.
    """
    sequence = [
        _full_intensity_setpoint(),
        # UP prep on the whole cloud: |g,0> -> |e,+1>.
        pi(Beam.UP, m=0, label="launch"),
        # Remove the residual un-transferred |g,0> so the image is clean.
        Clearout(),
        # DOWN pi addressing the excited m=1 population: |e,+1> -> |g,+2>.
        pi(Beam.DOWN, m=1, label="launch"),
        Wait(param="flight_time", label="flight"),
    ]
    return _build_roicheck_frag(sequence)


RoiCheckUp1ClrDown = _make_up_prep_clearout_down()
RoiCheckUp1ClrDown.__name__ = "RoiCheckUp1ClrDown"
RoiCheckUp1ClrDown.__qualname__ = "RoiCheckUp1ClrDown"

# Velocity-SLICED 2-recoil variant: a weak/long velocity-selective slice pi on
# m=0 (+1 recoil) -> clearout of the un-sliced atoms -> full-Rabi launch pi
# (+1 recoil), ending at the imageable ground state |g,+2>. A clean
# confirmation that 2 photon recoils were imparted to a narrow velocity class.
RoiCheckUp2Sliced = _make_sliced()
RoiCheckUp2Sliced.__name__ = "RoiCheckUp2Sliced"
RoiCheckUp2Sliced.__qualname__ = "RoiCheckUp2Sliced"

# Velocity-SLICED no-net-launch BASELINE: identical slice + clearout to
# RoiCheckUp2Sliced, but the final pi RETURNS the selected class to |g,0>
# (zero net momentum) instead of launching it to |g,+2>. Same pulse count and
# sequence duration as RoiCheckUp2Sliced, so differencing the two trajectories
# isolates exactly the launch recoils (slice velocity + duration cancel).
RoiCheckSlicedBaseline = _make_sliced_baseline()
RoiCheckSlicedBaseline.__name__ = "RoiCheckSlicedBaseline"
RoiCheckSlicedBaseline.__qualname__ = "RoiCheckSlicedBaseline"

# -- Configurable sliced launch-ladder build-up -------------------------------
#
# The momentum-class buildup is performed ONE LMT PULSE AT A TIME: a rig agent
# submits the n=1, then n=2, then n=3, ... variant, scanning the FINAL launch
# pulse's frequency offset at each step to confirm the cloud lands where the
# model predicts before adding the next pulse. The ladder NEVER skips an LMT.
#
# The ladder length is configurable via the module-level factory
# `_make_sliced_launch(n)` (the "build-arg" knob: each value of n yields a
# fragment whose declared lmt_sequence carries exactly n launch pulses). It is
# deliberately NOT an ndscan-scannable param: the slice/clearout/launch event
# set - and therefore the per-pulse offset/duration params and the compiled
# momentum walk - is fixed at build time and changes with n, so n cannot be a
# runtime scan axis. Named convenience classes for n = 1, 2, 3 are provided
# below so a rig agent can submit them directly by repo_rev.
#
# `RoiCheckUp2Sliced` above is the n=1 case (slice +1, launch pi +1 -> |g,+2>);
# the n=1 convenience alias below points at the same construction for a uniform
# naming scheme.

# n=1: slice (|e,+1>) -> clearout -> DOWN m=1 -> |g,+2> (single launch pulse).
RoiCheckSlicedLaunch1 = _make_sliced_launch(n=1)
RoiCheckSlicedLaunch1.__name__ = "RoiCheckSlicedLaunch1"
RoiCheckSlicedLaunch1.__qualname__ = "RoiCheckSlicedLaunch1"

# n=2: ... -> DOWN m=1 -> UP m=2 -> |e,+3> (two launch pulses).
RoiCheckSlicedLaunch2 = _make_sliced_launch(n=2)
RoiCheckSlicedLaunch2.__name__ = "RoiCheckSlicedLaunch2"
RoiCheckSlicedLaunch2.__qualname__ = "RoiCheckSlicedLaunch2"

# n=3: ... -> DOWN m=1 -> UP m=2 -> DOWN m=3 -> |g,+4> (three launch pulses).
RoiCheckSlicedLaunch3 = _make_sliced_launch(n=3)
RoiCheckSlicedLaunch3.__name__ = "RoiCheckSlicedLaunch3"
RoiCheckSlicedLaunch3.__qualname__ = "RoiCheckSlicedLaunch3"

# ndscan scan experiments (both the Frag and the scan-exp are module globals).
RoiCheckFallExp = make_fragment_scan_exp(RoiCheckFall)
RoiCheckUpExp = make_fragment_scan_exp(RoiCheckUp)
RoiCheckDownExp = make_fragment_scan_exp(RoiCheckDown)
RoiCheckUp2Exp = make_fragment_scan_exp(RoiCheckUp2)
RoiCheckUp8Exp = make_fragment_scan_exp(RoiCheckUp8)
RoiCheckUp1Exp = make_fragment_scan_exp(RoiCheckUp1)
RoiCheckDown1Exp = make_fragment_scan_exp(RoiCheckDown1)
RoiCheckUp1ClrDownExp = make_fragment_scan_exp(RoiCheckUp1ClrDown)
RoiCheckUp2SlicedExp = make_fragment_scan_exp(RoiCheckUp2Sliced)
RoiCheckSlicedBaselineExp = make_fragment_scan_exp(RoiCheckSlicedBaseline)
RoiCheckSlicedLaunch1Exp = make_fragment_scan_exp(RoiCheckSlicedLaunch1)
RoiCheckSlicedLaunch2Exp = make_fragment_scan_exp(RoiCheckSlicedLaunch2)
RoiCheckSlicedLaunch3Exp = make_fragment_scan_exp(RoiCheckSlicedLaunch3)
