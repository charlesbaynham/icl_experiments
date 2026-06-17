"""
Dual (gradiometer) LMT interferometer driven by the declarative sequence
language (deliverable D6).

A single dipole-trap cloud is launched up the momentum ladder to ``M_TOP``; a
splitting ``pi2`` makes two momentum classes; a separation ladder + dark time
drives them far enough apart that the two clouds resolve as separate spots on
the camera; then a wide-arm LMT interferometer (``N_BS`` recoils per beam
splitter) is run on BOTH clouds, interleaved about a common, time-symmetric
mirror. The two interferometers' phases subtract, giving a gradiometer; the
readout is the differential imbalance (``atom_number_imbalance``) between the
two clouds' output-port pairs.

This is the declarative translation of the legacy double-launch double
Mach-Zehnder / :class:`LMTSymmetricInterferometryMixin` (reference run
RID 74397).

Stack: D3's dipole-trap declarative stack
(:class:`~repository.LMT.lmt_declarative.DeclarativeLMTMachZehnderFrag`) with
ONE substitution - the single-cloud dynamic-ROI imaging mixin
(``NormalisedFastKineticsLMTCorrectedMixin``) is replaced by the two-trap
fast-kinetics readout ``DoubleTrapImagingClockPulseNormalisedMixin``. That mixin
places one fast-kinetics ROI pair (ground + excited) on each of the two clouds
(forward / backward dipole-trap ROIs, via 8 scannable IntParams) and pushes
per-cloud excitation fractions plus their differential ``atom_number_imbalance``
- exactly the gradiometer readout. It is the same imaging mixin the legacy
double-MZ reference (``LMTInterferometryWithShapedDoubleLaunchFrag``) uses on
this dipole base. The single-cloud LMT-corrected mixin cannot resolve two
spatially separated clouds (its trajectory predictor collapses all ground /
excited branches into one mean ROI each), so the swap is required, not optional.

The per-cloud wide-arm interferometer mirrors Agent-B's verified D5 geometry
(``build_single_lmt_interferometer`` in
``repository/LMT/declarative_interferometers.py``): the prefix helpers below are
copied from B's file verbatim so this experiment is self-contained (the live
checkout runs one branch at a time, so cross-branch imports are avoided). The
dual builder applies B's compiler-tracked arm-laddering technique to BOTH clouds
at once around a shared mirror. Closure is asserted host-side at import.
"""

from artiq.language import kernel
from ndscan.experiment.entry_point import make_fragment_scan_exp

from repository.lib import constants
from repository.lib.experiment_templates.dipole_trap_experiment import (
    DipoleTrapWithExperimentBase,
)
from repository.lib.experiment_templates.mixins.andor_imaging.double_trap_imaging import (
    DoubleTrapImagingClockPulseNormalisedMixin,
)
from repository.lib.experiment_templates.mixins.andor_imaging.em_gain import EMGainMixin
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
from repository.lib.lmt_sequence import Pulse
from repository.lib.lmt_sequence import SetPoint
from repository.lib.lmt_sequence import Wait
from repository.lib.lmt_sequence import compile_sequence
from repository.lib.lmt_sequence import ladder
from repository.lib.lmt_sequence import pi
from repository.lib.lmt_sequence import pi2

CLOCK_BEAM_DELIVERY_INFO = constants.SUSERVOED_BEAMS["clock_delivery"]

# Launch: the velocity-selective pulse provides the first kick, so the launch
# ladder runs from m = 1 and ends at m = 1 + N_LAUNCH.
N_LAUNCH = 12
M_TOP = 1 + N_LAUNCH

# LMT depth: photon recoils each interferometer arm is opened by. Start small
# (2 hbar k) to confirm closure + fringes; raise once contrast and timing allow.
N_BS = 2

# Dark time after the separation ladder, letting the two clouds physically
# drift apart before the interferometers run. At ~6.6 mm/s per recoil and a
# ~8-recoil velocity gap, ~10 ms drifts them ~33 um ~ 33 px apart - enough to
# land in the distinct forward / backward camera ROIs. Scannable on the rig
# (its spawned parameter is p<NN>_wait_separate_duration).
SEPARATION_TIME = 10e-3


# --- D3/D5 prefix helpers (copied verbatim from Agent-B's verified
# declarative_interferometers.py so this experiment is self-contained) ---


def _slice_setpoint():
    """The reduced-intensity velocity-slice set point (D3's first SetPoint)."""
    return SetPoint(
        setpoint=constants.CLOCK_SHELVING_PULSE_SETPOINT,
        rabi_up=1 / (2 * constants.CLOCK_SHELVING_PULSE_TIME),
        label="slice",
    )


def _full_intensity_setpoint():
    """Full-intensity set point for launch and interferometry (D3's second)."""
    return SetPoint(
        setpoint=CLOCK_BEAM_DELIVERY_INFO.setpoint,
        rabi_up=1 / (2 * constants.CLOCK_PI_TIME),
        rabi_down=1 / (2 * constants.DOWN_CLOCK_BEAM_PI_TIME),
    )


def _slice_launch_prefix():
    """The shared D3 prefix: slice -> full SetPoint -> Clearout -> launch ladder
    -> Clearout. Ends with the atoms excited at ``M_TOP``."""
    return [
        _slice_setpoint(),
        pi(Beam.UP, m=0, label="slice"),
        _full_intensity_setpoint(),
        Clearout(),
        *ladder(start_m=1, n=N_LAUNCH, first_beam=Beam.DOWN),
        Clearout(),
    ]


# --- D6 dual-interferometer builder ---


def _separation_for(n_bs):
    """Recoils of velocity difference opened between the two clouds.

    Must be odd (so the upper cloud's parked arm ends excited, matching the
    lower cloud) and large enough that the two clouds' LMT arms never overlap in
    momentum (>= 2 * n_bs + 1); a floor of 7 gives the smallest case a healthy
    spatial separation. At ~6.6 mm/s per recoil over the separation wait this
    drifts the clouds tens of px apart - far more than the bare ~1 px a
    1-recoil split would give - so they land in distinct camera ROIs.
    """
    sep = max(7, 2 * int(n_bs) + 1)
    if sep % 2 == 0:
        sep += 1
    return sep


def _build_separation(sep):
    """Split the launched cloud and walk the upper class up by ``sep`` recoils.

    Returns ``(pulses, m_lo, m_hi)``: the splitting ``pi2`` leaves the lower
    cloud parked at ``(e, M_TOP)`` and the upper moving arm at ``(g, M_TOP+1)``;
    the ladder then walks that arm up ``sep`` recoils (up from ground, down from
    excited), ending the upper cloud's parked arm at ``(e, M_TOP + 1 + sep)``.
    ``sep`` odd guarantees both parked arms are excited.
    """
    assert sep % 2 == 1, "separation must be odd so both parked arms end excited"
    pulses = [pi2(Beam.DOWN, m=M_TOP, state="e", label="split")]
    m = M_TOP + 1
    state = "g"
    for j in range(sep):
        if state == "g":
            pulses.append(pi(Beam.UP, m=m, state="g", label=f"sep{j}"))
            state = "e"
        else:
            pulses.append(pi(Beam.DOWN, m=m, state="e", label=f"sep{j}"))
            state = "g"
        m += 1
    return pulses, M_TOP, M_TOP + 1 + sep


def build_dual_lmt_interferometer(n_bs):
    """Build the full D6 sequence: launch, split, separate, dual wide-arm MZ.

    After the launch and separation the two clouds are parked excited at
    ``m_lo = M_TOP`` and ``m_hi = M_TOP + 1 + sep``. A wide-arm LMT Mach-Zehnder
    is then run on EACH cloud, interleaved about a common pair of dark times and
    mirror, so the two interferometers share their timing (common-mode
    rejection - the point of a gradiometer). Each cloud closes to the two ports
    ``{(e, m), (g, m + 1)}``, so the full sequence closes to four ports.

    The moving arm of each cloud is tracked through the sequence compiler (the
    technique from Agent-B's ``build_single_lmt_interferometer``): every laddered
    pulse is addressed by the resolved ``(state, m)`` of that cloud's moving arm,
    not a hand-rolled sign rule. The two clouds are kept >= ``2 * n_bs + 1``
    recoils apart so their arms never share an ``(state, m)``.
    """
    sep = _separation_for(n_bs)
    prefix, m_lo, m_hi = _build_separation(sep)
    init = {("e", M_TOP)}
    parked = {("e", m_lo), ("e", m_hi)}

    seq = list(prefix)

    # Let the two clouds drift apart spatially before the interferometers run.
    seq.append(Wait(t=SEPARATION_TIME, label="separate"))

    def opposite(beam):
        return Beam.DOWN if beam is Beam.UP else Beam.UP

    def follow(prev):
        """Resolve the current ``(state, m)`` of a cloud's moving arm.

        The arm moves at most one recoil per pulse, so it is the populated
        non-parked state nearest the previous position. Tracked via the compiler
        so the recoil bookkeeping is exact.
        """
        compiled = compile_sequence(
            [_full_intensity_setpoint()] + seq, initial_population=set(init)
        )
        candidates = [p for p in compiled.final_population if p not in parked]
        candidates.sort(key=lambda p: abs(p[1] - prev[1]))
        assert candidates and abs(candidates[0][1] - prev[1]) <= 1, (
            f"lost the moving arm near {prev}: " f"{sorted(compiled.final_population)}"
        )
        return candidates[0]

    # Beam splitter on each cloud (selective via state= on the parked excited
    # arm). The down-beam pi2 leaves each cloud's moving arm at (g, m + 1).
    seq.append(pi2(Beam.DOWN, m=m_lo, state="e", label="bs_lo"))
    seq.append(pi2(Beam.DOWN, m=m_hi, state="e", label="bs_hi"))
    arm_lo = ("g", m_lo + 1)
    arm_hi = ("g", m_hi + 1)

    # Opening ladders: walk each moving arm up n_bs - 1 further recoils,
    # interleaving the two clouds. Record the beams to reverse for the mirror.
    out_lo = []
    out_hi = []
    beam_lo = Beam.UP
    beam_hi = Beam.UP
    for _ in range(int(n_bs) - 1):
        state, m = arm_lo
        seq.append(Pulse(1.0, beam_lo, m, state=state, label="open_lo"))
        out_lo.append(beam_lo)
        arm_lo = follow(arm_lo)
        beam_lo = opposite(beam_lo)

        state, m = arm_hi
        seq.append(Pulse(1.0, beam_hi, m, state=state, label="open_hi"))
        out_hi.append(beam_hi)
        arm_hi = follow(arm_hi)
        beam_hi = opposite(beam_hi)

    seq.append(Wait(t=1e-3, label="dark1"))

    # Common mirror: reverse each opening ladder (same beam on the current
    # apex-side arm walks it one recoil back home), interleaved across clouds so
    # both interferometers fold about the same dark-time midpoint.
    for beam in reversed(out_lo):
        state, m = arm_lo
        seq.append(Pulse(1.0, beam, m, state=state, label="mir_lo"))
        arm_lo = follow(arm_lo)
    for beam in reversed(out_hi):
        state, m = arm_hi
        seq.append(Pulse(1.0, beam, m, state=state, label="mir_hi"))
        arm_hi = follow(arm_hi)

    seq.append(Wait(t=1e-3, label="dark2"))

    # Recombiners (one per cloud).
    seq.append(pi2(Beam.DOWN, m=m_lo, state="e", label="bs2_lo"))
    seq.append(pi2(Beam.DOWN, m=m_hi, state="e", label="bs2_hi"))
    return seq, m_lo, m_hi


_DUAL_SEQUENCE, _M_LO, _M_HI = build_dual_lmt_interferometer(N_BS)

# Host-side closure assertion (D6): the dual interferometer closes to the four
# expected ports - two per cloud. Runs at import; mirrors the closure asserts in
# tests/test_lmt_sequence.py and tests/test_declarative_interferometers.py.
_EXPECTED_PORTS = frozenset(
    {("e", _M_LO), ("g", _M_LO + 1), ("e", _M_HI), ("g", _M_HI + 1)}
)
_compiled_d6 = compile_sequence(
    [*_slice_launch_prefix(), *_DUAL_SEQUENCE], initial_population={("g", 0)}
)
assert _compiled_d6.final_population == _EXPECTED_PORTS, (
    "D6 dual interferometer does not close to the expected differential ports: "
    f"got {sorted(_compiled_d6.final_population)}, want {sorted(_EXPECTED_PORTS)}"
)


class DeclarativeLMTDualInterferometerFrag(
    DeclarativeLMTBase,
    # Two-trap fast-kinetics readout: one ground+excited ROI pair on each of the
    # two spatially separated clouds (forward / backward dipole-trap ROIs),
    # pushing per-cloud excitation fractions and their differential
    # atom_number_imbalance. Replaces D3's single-cloud dynamic-ROI mixin, which
    # cannot resolve two clouds. Same mixin the legacy double-MZ reference uses
    # on this dipole base. NB: do not enable do_gauss_fit with this triple-FK
    # family (RuntimeError: result channel already pushed).
    DoubleTrapImagingClockPulseNormalisedMixin,
    EMGainMixin,
    LoadSingleXODTMixin,
    XODTSingleMolassesPlusDipoleRampMixin,
    OpticalPumpingWithFieldSettingDipoleTrapMixin,
    FieldOnlyRampInEvapMixin,
    DipoleTrapWithExperimentBase,
):
    """Launch, split, separate and a dual (gradiometer) LMT interferometer."""

    # Atoms are released from the trap in the ground state with no kicks
    lmt_initial_population = {("g", 0)}

    lmt_sequence = [
        *_slice_launch_prefix(),
        *_DUAL_SEQUENCE,
    ]

    def build_fragment(self):
        super().build_fragment()
        # Run with conventional (non-EM) gain. The DISABLE_EM_GAIN camera
        # safety interlock is set on the live master, so em_gain_enabled must
        # be False; EMGainMixin otherwise defaults it True and its host_setup
        # interlock check raises. This only overrides the parameter default
        # (still scannable); it never reads, writes or bypasses DISABLE_EM_GAIN.
        self.override_param("em_gain_enabled", False)

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


DeclarativeLMTDualInterferometer = make_fragment_scan_exp(
    DeclarativeLMTDualInterferometerFrag
)
