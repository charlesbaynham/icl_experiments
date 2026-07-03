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
