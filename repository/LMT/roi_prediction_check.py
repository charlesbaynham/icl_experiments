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

# ndscan scan experiments (both the Frag and the scan-exp are module globals).
RoiCheckFallExp = make_fragment_scan_exp(RoiCheckFall)
RoiCheckUpExp = make_fragment_scan_exp(RoiCheckUp)
RoiCheckDownExp = make_fragment_scan_exp(RoiCheckDown)
RoiCheckUp2Exp = make_fragment_scan_exp(RoiCheckUp2)
RoiCheckUp8Exp = make_fragment_scan_exp(RoiCheckUp8)
RoiCheckUp2SlicedExp = make_fragment_scan_exp(RoiCheckUp2Sliced)
RoiCheckSlicedBaselineExp = make_fragment_scan_exp(RoiCheckSlicedBaseline)
