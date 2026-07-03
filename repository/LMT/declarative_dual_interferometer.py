"""
Declarative LMT cloud split (milestone B1).

Split one launched cloud into two spatially-resolved clouds at DIFFERENT
momenta, both parked excited, so they drift apart ballistically and can be read
out by their own camera ROI. This is the split-only step (no interferometer);
the interferometer on both clouds is milestone C1.

Geometry (recoil-gap, the prior 2026-06-20 approach, kept because its
separation-vs-wait slope is directly diagnostic):

    launch to M_TOP  ->  pi/2 split  ->  ladder walks the upper class up `sep`
    recoils  ->  dark wait (clouds drift apart)  ->  image.

The two clouds end parked at ``(e, M_TOP)`` and ``(e, M_TOP + 1 + sep)``; their
velocity gap is ``(1 + sep)`` recoils, so the spatial separation grows linearly
with the dark wait. A host-side sim (scratch/split_sep_sim.py) puts M_TOP=5,
sep=19 at ~33 px separation after a 4 ms wait - above the ~30 px single-cloud
width - at ~88 % launch+split survival, comfortably inside the M_TOP~=5 loss
budget the card calls for.

DISCRIMINATOR intent: scan the `separate` dark wait and read both clouds' atom
numbers. Ballistic growth (slope ~ velocity gap) vs a flat/fixed offset tells
split-works-but-mis-imaged from an inefficient ladder; the two clouds' atom-#
ratio measures the pi/2 beamsplitter efficiency directly.

Readout / imaging: reuses ``NormalisedFastKineticsLMTCorrectedMixin`` - the
2026-07-01 clock-pulse working point (full-power broad M-state-selection DOWN pi
+ free-fall gravity OPLL chirp) that this branch reinstated onto the
declarative-lmt tip. Its single dynamic ROI is centred on the excited-port mean
(the predictor collapses the two excited branches to their mean, flagged
multiplicity 2); both clouds sit inside one fast-kinetics sub-frame at these
separations, so ``save_raw_andor_image=True`` + an offline two-blob fit gives
per-cloud atom numbers and the two-ROI overlay photo. (A dedicated two-ROI
readout is deferred to C1, once the split is proven.)
"""

import logging

from artiq.language import kernel
from ndscan.experiment.entry_point import make_fragment_scan_exp

from repository.lib import constants
from repository.lib.experiment_templates.dipole_trap_experiment import (
    DipoleTrapWithExperimentBase,
)
from repository.lib.experiment_templates.mixins.andor_imaging.em_gain import EMGainMixin
from repository.lib.experiment_templates.mixins.andor_imaging.lmt_compensated_normalised_imaging import (  # noqa: E501
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
from repository.lib.lmt_sequence import ladder
from repository.lib.lmt_sequence import pi
from repository.lib.lmt_sequence import pi2
from repository.lib.physics.lmt_resonance import EXCITED
from repository.lib.physics.lmt_resonance import GROUND

logger = logging.getLogger(__name__)

CLOCK_BEAM_DELIVERY_INFO = constants.SUSERVOED_BEAMS["clock_delivery"]

# Launch height. The velocity-selective pulse provides the first kick, so the
# ladder runs m = 1 .. M_TOP. Kept shallow (card: M_TOP ~= 5); the M_TOP = 13
# dual path was too lossy.
N_LAUNCH = 4
M_TOP = 1 + N_LAUNCH

# Post-launch drop so the cloud falls back into the fast-kinetics window before
# the split (mirrors the symmetric-MZ working point).
DROP = 100e-6

# Default dark wait after the separation ladder. Labelled so ndscan spawns a
# scannable `separate` duration - the discriminator axis.
SEPARATION_TIME = 4e-3


def _slice_launch_prefix():
    """Slice -> full SetPoint -> Clearout -> launch ladder -> Clearout -> drop.

    Identical to the symmetric-MZ working point; ends excited at ``M_TOP``.
    """
    return [
        SetPoint(
            setpoint=constants.CLOCK_SHELVING_PULSE_SETPOINT,
            rabi_up=1 / (2 * constants.CLOCK_SHELVING_PULSE_TIME),
            label="slice",
        ),
        pi(Beam.UP, m=0, label="slice"),
        SetPoint(
            setpoint=CLOCK_BEAM_DELIVERY_INFO.setpoint,
            rabi_up=1 / (2 * constants.CLOCK_PI_TIME),
            rabi_down=1 / (2 * constants.DOWN_CLOCK_BEAM_PI_TIME),
        ),
        Clearout(),
        *ladder(start_m=1, n=N_LAUNCH, first_beam=Beam.DOWN, clearout_from=-4),
        Clearout(),
        Wait(t=DROP, label="droptime"),
    ]


def _split_and_separate(sep, separation_time):
    """pi/2 split then walk the upper class up ``sep`` recoils, then dark wait.

    ``sep`` must be odd so the upper cloud's parked arm ends excited, matching
    the lower cloud parked at ``(e, M_TOP)``. The split leaves the lower cloud
    at ``(e, M_TOP)`` and the moving upper arm at ``(g, M_TOP + 1)``; the ladder
    (up beam from ground, down beam from excited) raises it to
    ``(e, M_TOP + 1 + sep)``.
    """
    if sep % 2 != 1:
        raise ValueError("sep must be odd so both parked arms end excited")
    pulses = [pi2(Beam.DOWN, m=M_TOP, state=EXCITED, label="split")]
    m = M_TOP + 1
    state = GROUND
    for j in range(sep):
        if state == GROUND:
            pulses.append(pi(Beam.UP, m=m, state=GROUND, label="sep%d" % j))
            state = EXCITED
        else:
            pulses.append(pi(Beam.DOWN, m=m, state=EXCITED, label="sep%d" % j))
            state = GROUND
        m += 1
    pulses.append(Wait(t=separation_time, label="separate"))
    return pulses


def _split_sequence(sep, separation_time=SEPARATION_TIME):
    return [*_slice_launch_prefix(), *_split_and_separate(sep, separation_time)]


class _SplitOnlyBase(
    DeclarativeLMTBase,
    NormalisedFastKineticsLMTCorrectedMixin,
    EMGainMixin,
    LoadSingleXODTMixin,
    XODTSingleMolassesPlusDipoleRampMixin,
    OpticalPumpingWithFieldSettingDipoleTrapMixin,
    FieldOnlyRampInEvapMixin,
    DipoleTrapWithExperimentBase,
):
    """Launch, split and separate two clouds - no interferometer (milestone B1).

    Subclasses bake ``lmt_sequence`` (its length fixes the spawned per-pulse
    params and kernel array sizes, so the separation depth is a code constant,
    like the zigzag ladder).
    """

    lmt_initial_population = {(GROUND, 0)}

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


class DeclarativeLMTSplitDiscriminatorFrag(_SplitOnlyBase):
    """B1 discriminator: M_TOP=5, sep=19 (20-recoil velocity gap).

    Sim: ~33 px separation at a 4 ms `separate` wait, ~88 % launch+split
    survival. Scan the spawned `separate` duration (~2-8 ms) to read the
    separation-vs-wait slope and both clouds' atom numbers.
    """

    lmt_sequence = _split_sequence(sep=19)


class DeclarativeLMTSplitWideFrag(_SplitOnlyBase):
    """Wider margin: M_TOP=5, sep=27 (28-recoil gap), ~46 px at 4 ms, ~84 %
    survival - for a cleanly resolved two-cloud photo once the split is proven.
    """

    lmt_sequence = _split_sequence(sep=27)


DeclarativeLMTSplitDiscriminator = make_fragment_scan_exp(
    DeclarativeLMTSplitDiscriminatorFrag, max_rtio_underflow_retries=0
)
DeclarativeLMTSplitWide = make_fragment_scan_exp(
    DeclarativeLMTSplitWideFrag, max_rtio_underflow_retries=0
)


# ---------------------------------------------------------------------------
# Selective-pulse machinery
# ---------------------------------------------------------------------------
# Primary evidence from the 2026-06-20 split RIDs (75378-85) shows a single
# dim blob with a comet tail, not two clouds: the full-power ~56-68 us pulses
# (Fourier width ~ the 9.4 kHz recoil spacing) leak on pulses addressing pairs
# only ~2 spacings from a parked cloud, stranding population all along the
# separation ladder. The 2026-01..03 rig working point for frequency-selective
# pulses was ~95 us at reduced power (legacy path: 10.5 dB switch attenuation).
#
# At a shared delivery set point the down beam cannot be attenuated
# independently (the legacy path balanced the switch-AOM attenuations, 13 dB
# up / 12.5 dB down, to equalise durations), so here the down pi time scales
# with the same delivery-intensity factor instead of matching 95 us exactly.
# All durations/setpoints spawn as scannable params for rig tuning.

SELECTIVE_PI_TIME = 95e-6
_SELECTIVE_INTENSITY_SCALE = (constants.CLOCK_PI_TIME / SELECTIVE_PI_TIME) ** 2
SELECTIVE_SETPOINT = CLOCK_BEAM_DELIVERY_INFO.setpoint * _SELECTIVE_INTENSITY_SCALE
SELECTIVE_RABI_UP = 1 / (2 * SELECTIVE_PI_TIME)
SELECTIVE_RABI_DOWN = (1 / (2 * constants.DOWN_CLOCK_BEAM_PI_TIME)) * (
    constants.CLOCK_PI_TIME / SELECTIVE_PI_TIME
)


def _selective_setpoint(label="selective"):
    return SetPoint(
        setpoint=SELECTIVE_SETPOINT,
        rabi_up=SELECTIVE_RABI_UP,
        rabi_down=SELECTIVE_RABI_DOWN,
        label=label,
    )


def _full_setpoint(label=""):
    return SetPoint(
        setpoint=CLOCK_BEAM_DELIVERY_INFO.setpoint,
        rabi_up=1 / (2 * constants.CLOCK_PI_TIME),
        rabi_down=1 / (2 * constants.DOWN_CLOCK_BEAM_PI_TIME),
        label=label,
    )


def _split_and_separate_selective(sep, separation_time, n_selective):
    """As :func:`_split_and_separate`, with the split pi/2 and the first
    ``n_selective`` separation pulses at the reduced-power selective set point.

    Those pulses address pairs only ~2 recoil spacings from the parked cloud,
    where the full-power pulses are Fourier-broad enough to leak (the comet
    tail); from ``n_selective`` onwards the moving arm is far enough detuned
    for full power. The extra SetPoints cost two servo settles - irrelevant
    here (no interferometer to keep symmetric).
    """
    if sep % 2 != 1:
        raise ValueError("sep must be odd so both parked arms end excited")
    if not 1 <= n_selective <= sep:
        raise ValueError("n_selective must be in 1..sep")
    events = [
        _selective_setpoint("split"),
        pi2(Beam.DOWN, m=M_TOP, state=EXCITED, label="split"),
    ]
    m = M_TOP + 1
    state = GROUND
    for j in range(sep):
        if j == n_selective:
            events.append(_full_setpoint("sepfull"))
        if state == GROUND:
            events.append(pi(Beam.UP, m=m, state=GROUND, label="sep%d" % j))
            state = EXCITED
        else:
            events.append(pi(Beam.DOWN, m=m, state=EXCITED, label="sep%d" % j))
            state = GROUND
        m += 1
    events.append(Wait(t=separation_time, label="separate"))
    return events


class DeclarativeLMTSplitSelectiveFrag(_SplitOnlyBase):
    """Geometry-A split with SELECTIVE split + early-separation pulses.

    Identical recoil-gap geometry to :class:`DeclarativeLMTSplitDiscriminatorFrag`
    (M_TOP=5, sep=19, ~33 px at a 4 ms wait) but the split pi/2 and first 3
    separation pulses run at the 95 us selective working point. If ladder
    leakage caused the prior comet tail, this converts it into a clean second
    cloud; compare against the full-power discriminator at the same wait.
    """

    lmt_sequence = [
        *_slice_launch_prefix(),
        *_split_and_separate_selective(
            sep=19, separation_time=SEPARATION_TIME, n_selective=3
        ),
    ]


DeclarativeLMTSplitSelective = make_fragment_scan_exp(
    DeclarativeLMTSplitSelectiveFrag, max_rtio_underflow_retries=0
)


# ---------------------------------------------------------------------------
# Geometry B - same-momentum split (the job card's recipe)
# ---------------------------------------------------------------------------
# pi/2 -> climb arm B (launch) -> wait -> climb arm A (launch) -> final pi/2
# -> clear out the ground state => two clouds in the SAME momentum state, both
# excited. The spatial separation comes from the inter-arm WAIT (arm B moves
# at M_B recoils while arm A parks at 1), so no long separation ladder runs
# with a parked cloud nearby: only the ~2 pulses at each ladder's near end
# need selectivity. The merge pi/2 addresses the pair holding BOTH arms - (g,
# M_B-1) from arm A and (e, M_B) from arm B - so each cloud pays the 50 %
# clearout cost, leaving two EQUAL-brightness clouds at (e, M_B). That cost is
# the geometry's price for ending at identical momentum (the card's spec).
#
# Separation = (M_B - 1) recoils x the `separate` wait ~ 3.3 px/ms at M_B=9
# (26 px at the 8 ms default; scan 4-12 ms). Survival ~92 % over the 16 pi
# pulses, then the merge halves each arm.

M_B = 9  # must be odd so both ladders end in the merge pair
SEPARATION_TIME_B = 8e-3


def _climb(m_start, state_start, n, label_prefix):
    """n alternating-beam pi pulses walking one arm up from (state, m) by n
    recoils, each tagged with its arm's state (two branches are populated, so
    implicit resolution is not available)."""
    pulses = []
    m = m_start
    state = state_start
    for j in range(n):
        if state == GROUND:
            pulses.append(
                pi(Beam.UP, m=m, state=GROUND, label="%s%d" % (label_prefix, j))
            )
            state = EXCITED
        else:
            pulses.append(
                pi(Beam.DOWN, m=m, state=EXCITED, label="%s%d" % (label_prefix, j))
            )
            state = GROUND
        m += 1
    return pulses


def _same_momentum_sequence(m_top, separation_time):
    if m_top % 2 != 1:
        raise ValueError("m_top must be odd: both arms must meet in one pair")
    n_climb = m_top - 2  # arm B: (g,2)->(e,m_top); arm A: (e,1)->(g,m_top-1)
    arm_b = _climb(2, GROUND, n_climb, "b")
    arm_a = _climb(1, EXCITED, n_climb, "a")
    return [
        SetPoint(
            setpoint=constants.CLOCK_SHELVING_PULSE_SETPOINT,
            rabi_up=1 / (2 * constants.CLOCK_SHELVING_PULSE_TIME),
            label="slice",
        ),
        pi(Beam.UP, m=0, label="slice"),
        _full_setpoint("clear"),
        Clearout(),
        # Split at (e,1): arm A parks there, arm B leaves at (g,2)
        _selective_setpoint("split"),
        pi2(Beam.DOWN, m=1, state=EXCITED, label="split"),
        # Arm B climbs to (e, m_top); its first 2 pulses sit ~2 recoil
        # spacings from parked arm A -> selective, rest full power
        *arm_b[:2],
        _full_setpoint("bfull"),
        *arm_b[2:],
        Clearout(),
        Wait(t=separation_time, label="separate"),
        # Arm A climbs to (g, m_top - 1); its last 2 pulses approach parked
        # arm B -> selective (the merge stays selective too)
        *arm_a[: n_climb - 2],
        _selective_setpoint("amerge"),
        *arm_a[n_climb - 2 :],
        # Merge: pi/2 on the pair (g, m_top-1) <-> (e, m_top) holding BOTH
        # arms; the ground halves are then cleared, leaving two equal clouds
        # parked at (e, m_top)
        pi2(Beam.UP, m=m_top - 1, state=GROUND, label="merge"),
        Clearout(),
    ]


class DeclarativeLMTSameMomentumSplitFrag(_SplitOnlyBase):
    """Milestone B1, the job card's geometry: two clouds, SAME momentum, both
    excited at (e, M_B), separation set by the scannable `separate` wait."""

    lmt_sequence = _same_momentum_sequence(M_B, SEPARATION_TIME_B)


DeclarativeLMTSameMomentumSplit = make_fragment_scan_exp(
    DeclarativeLMTSameMomentumSplitFrag, max_rtio_underflow_retries=0
)
