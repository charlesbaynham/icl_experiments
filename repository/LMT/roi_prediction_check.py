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

# ndscan scan experiments (both the Frag and the scan-exp are module globals).
RoiCheckFallExp = make_fragment_scan_exp(RoiCheckFall)
RoiCheckUpExp = make_fragment_scan_exp(RoiCheckUp)
RoiCheckDownExp = make_fragment_scan_exp(RoiCheckDown)
