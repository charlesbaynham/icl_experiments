"""
Split and large-momentum-transfer (LMT) interferometers driven by the
declarative sequence language.

Two deliverables built on the *exact* dipole-trap base/mixin stack of
:class:`~repository.LMT.lmt_declarative.DeclarativeLMTMachZehnderFrag` (D3),
reusing its launch (``N_LAUNCH`` alternating pi pulses to ``M_TOP``), its
shelving/slice set points and both kernel hooks verbatim:

* :class:`DeclarativeLMTDualMachZehnderFrag` (D4) - launch, a *splitting*
  ``pi2`` that makes two clouds at adjacent momentum classes, then a 3-pulse
  Mach-Zehnder run on *both* clouds (interleaved, momentum-selective). Readout
  is the imbalance between the two output ports.
* :class:`DeclarativeLMTSingleInterferometerFrag` (D5) - launch, then a single
  LMT Mach-Zehnder whose arms are opened by ``N_BS`` photon recoils. One arm is
  walked out and back over the dark times (the LMT excursion) while the other
  parks; the interferometer closes to the same two ports as the D3
  Mach-Zehnder.

Both sequences are validated host-side by
:func:`~repository.lib.lmt_sequence.compile_sequence` (see the closure
assertions in ``tests/test_declarative_interferometers.py``); the execution
engine (:class:`~repository.lib.experiment_templates.mixins.declarative_lmt.DeclarativeLMTBase`)
spawns the per-pulse ndscan parameters and fires them.
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
from repository.lib.lmt_sequence import Pulse
from repository.lib.lmt_sequence import SetPoint
from repository.lib.lmt_sequence import Wait
from repository.lib.lmt_sequence import compile_sequence
from repository.lib.lmt_sequence import ladder
from repository.lib.lmt_sequence import pi
from repository.lib.lmt_sequence import pi2

# Reuse D3's launch constants and delivery-beam info verbatim.
from repository.LMT.lmt_declarative import CLOCK_BEAM_DELIVERY_INFO
from repository.LMT.lmt_declarative import M_TOP
from repository.LMT.lmt_declarative import N_LAUNCH

# LMT depth for D5: number of photon recoils the interferometer arm is opened
# by. Start small (2 hbar k) to confirm closure + fringes; raise once contrast
# and timing allow (each extra recoil adds two pi pulses to the dark-time
# ladders and tightens the RTIO programming budget).
N_BS = 2

# D4 dual interferometer: after the splitting pi/2 the two clouds differ by one
# recoil only - far too close to resolve on camera. Drive them apart with N_SEP
# extra recoils on the upper cloud and let them drift for SEPARATION_WAIT before
# the two Mach-Zehnders, so they land in the forward / backward ROIs tens of
# pixels apart. One recoil is ~6.6 mm/s; N_SEP=6 over ~20 ms gives ~50 px of
# separation (ROI width 100 px), comfortably resolvable. Both are easily-raised
# module constants.
N_SEP = 6
SEPARATION_WAIT = 20e-3


def _slice_setpoint():
    """The reduced-intensity velocity-slice set point (D3's first SetPoint).

    Reduced intensity is done through the delivery SUServo set point; the
    value must be calibrated on atoms (Agent-A calibrates p00_setpoint_slice).
    """
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


def build_single_lmt_interferometer(n_bs, m_top=M_TOP):
    """Pulses for an asymmetric single LMT Mach-Zehnder on the pair
    ``(e, m_top)`` <-> ``(g, m_top + 1)``.

    The opening ``pi2`` (``bs``) splits the launched cloud into the parked arm
    ``(e, m_top)`` and the moving arm ``(g, m_top + 1)``. ``n_bs - 1`` further
    pi pulses (``bs_open``) walk the moving arm up the momentum ladder, so the
    two arms separate by ``n_bs`` recoils during the first dark time. The
    mirror is the ``2 * (n_bs - 1)``-pulse exact reverse of that ladder, walking
    the moving arm back down over the second dark time; the recombiner ``pi2``
    (``bs2``) closes the interferometer to the two ports
    ``{(e, m_top), (g, m_top + 1)}`` - identical to the D3 Mach-Zehnder, which
    is the ``n_bs == 1`` case.

    The arms never share an ``(internal_state, momentum_class)`` until
    recombination (the moving arm is always above the parked one), so the
    momentum-class bookkeeping stays unambiguous; ``state=`` is given on every
    laddered pulse to pin which arm it addresses. Built and verified against
    ``compile_sequence`` (see ``tests/test_declarative_interferometers.py``).
    """

    def opposite(beam):
        return Beam.DOWN if beam is Beam.UP else Beam.UP

    # We track the moving arm's resolved (state, m) via the compiler so the
    # ladder follows the *physical* recoil bookkeeping (an excited-state pulse
    # moves m in the opposite sense to a ground-state one), not a hand-rolled
    # sign rule. Compile a probe prefix from the launched population.
    probe_prefix = [_full_intensity_setpoint()]
    initial = {("e", m_top)}
    parked_state = ("e", m_top)

    def moving_arm(seq_tail):
        compiled = compile_sequence(
            probe_prefix + seq_tail, initial_population=set(initial)
        )
        others = [p for p in compiled.final_population if p != parked_state]
        assert len(others) == 1, (
            "single-interferometer build expected exactly one moving arm, got "
            f"{sorted(compiled.final_population)}"
        )
        return others[0]

    seq = [pi2(Beam.DOWN, m=m_top, label="bs")]
    out = []  # (beam, addressed_m, addressed_state) for each opening pulse
    beam = Beam.UP
    arm = moving_arm(seq)
    for _ in range(int(n_bs) - 1):
        addr_state, addr_m = arm
        seq.append(Pulse(1.0, beam, addr_m, state=addr_state, label="bs_open"))
        out.append((beam, addr_m, addr_state))
        arm = moving_arm(seq)
        beam = opposite(beam)

    seq.append(Wait(t=1e-3, label="d1"))

    # Mirror: exact reverse of the opening ladder. Firing the same beam on the
    # current (apex-side) arm returns it one recoil towards home.
    for beam_out, _addr_m_out, _addr_state_out in reversed(out):
        addr_state, addr_m = arm
        seq.append(Pulse(1.0, beam_out, addr_m, state=addr_state, label="mir"))
        arm = moving_arm(seq)

    seq.append(Wait(t=1e-3, label="d2"))
    seq.append(pi2(Beam.DOWN, m=m_top, label="bs2"))
    return seq


def build_dual_mach_zehnder(n_sep=N_SEP, separation_wait=SEPARATION_WAIT, m_top=M_TOP):
    """Pulses for D4: split the launched cloud, drive the two clouds apart, then
    run an independent 3-pulse Mach-Zehnder on each about a common mirror.

    The splitting ``pi2`` (``split``) makes a lower cloud ``(e, m_top)`` and an
    upper cloud ``(g, m_top + 1)``. ``n_sep`` further pi pulses (``sep``) ladder
    the upper cloud up the momentum ladder so the clouds differ by ``n_sep + 1``
    recoils; a ``separation_wait`` then lets them drift apart spatially (into the
    forward / backward camera ROIs) before any interferometry. Each cloud then
    gets its own beam splitter / mirror / recombiner (``*_lo`` for the lower,
    ``*_hi`` for the upper) sharing the two dark times, so the two
    interferometers are symmetric about a common mirror and close together. All
    interferometer pulses carry ``state=`` because the split and separation
    leave both internal states populated at neighbouring momentum classes.

    The upper cloud's resolved ``(state, m)`` is tracked through
    ``compile_sequence`` (the recoil sense depends on the internal state), so the
    separation ladder follows the physical momentum walk. Returns a sequence that
    closes to four ports - two per cloud.
    """

    def opposite(beam):
        return Beam.DOWN if beam is Beam.UP else Beam.UP

    probe_prefix = [_full_intensity_setpoint()]
    parked_state = ("e", m_top)

    def upper_cloud(seq_tail):
        compiled = compile_sequence(
            probe_prefix + seq_tail, initial_population={("e", m_top)}
        )
        others = [p for p in compiled.final_population if p != parked_state]
        assert len(others) == 1, (
            "dual build expected one upper cloud, got "
            f"{sorted(compiled.final_population)}"
        )
        return others[0]

    seq = [pi2(Beam.DOWN, m=m_top, label="split")]
    arm = upper_cloud(seq)
    beam = Beam.UP
    for _ in range(int(n_sep)):
        state, m = arm
        seq.append(Pulse(1.0, beam, m, state=state, label="sep"))
        arm = upper_cloud(seq)
        beam = opposite(beam)

    lower_m = m_top
    upper_state, upper_m = arm
    seq.append(Wait(t=separation_wait, label="separation"))

    # 3-pulse Mach-Zehnder on each cloud, sharing the two dark times / mirror.
    seq += [
        pi2(Beam.UP, m=lower_m, state="e", label="bs1_lo"),
        pi2(Beam.UP, m=upper_m, state=upper_state, label="bs1_hi"),
        Wait(t=1e-3, label="dark1"),
        pi(Beam.UP, m=lower_m, label="mir_lo"),
        pi(Beam.UP, m=upper_m, label="mir_hi"),
        Wait(t=1e-3, label="dark2"),
        pi2(Beam.UP, m=lower_m, label="bs2_lo"),
        pi2(Beam.UP, m=upper_m, label="bs2_hi"),
    ]
    return seq


class DeclarativeLMTDualMachZehnderFrag(
    DeclarativeLMTBase,
    # Two spatially-separated clouds: the static-config double-trap imaging mixin
    # places a forward + backward ROI (8 scannable IntParams) and reads
    # per-cloud excitation fractions and atom_number_imbalance. Replaces D3's
    # single-cloud dynamic-ROI NormalisedFastKineticsLMTCorrectedMixin.
    DoubleTrapImagingClockPulseNormalisedMixin,
    EMGainMixin,
    LoadSingleXODTMixin,
    XODTSingleMolassesPlusDipoleRampMixin,
    OpticalPumpingWithFieldSettingDipoleTrapMixin,
    FieldOnlyRampInEvapMixin,
    DipoleTrapWithExperimentBase,
):
    """
    D4: launch, split into two clouds, drive them apart, then a dual Mach-Zehnder.

    After the launch the cloud is excited at ``M_TOP``. A splitting ``pi2``
    (``split``) makes a lower cloud ``(e, M_TOP)`` and an upper cloud
    ``(g, M_TOP + 1)``; ``N_SEP`` further pi pulses (``sep``) ladder the upper
    cloud up so the two clouds separate by ``N_SEP + 1`` recoils, and a
    ``SEPARATION_WAIT`` lets them drift into the forward / backward camera ROIs
    before any interferometry. An independent 3-pulse Mach-Zehnder then runs on
    each cloud about a common pair of dark times / mirror (``*_lo`` lower,
    ``*_hi`` upper); every interferometer pulse carries ``state=`` to pin which
    population it addresses.

    The two interferometers close to four distinct ports (two per cloud); the
    readout (``DoubleTrapImagingClockPulseNormalisedMixin``) is the per-cloud
    excitation fraction and the forward/backward ``atom_number_imbalance``. No
    SetPoint/Clearout falls between the first and last beam splitters and the two
    dark times are symmetric about the mirror, so both interferometers close.
    The 8 ROI IntParams default to the dipole double-trap positions and are
    scanned/tuned onto the two clouds' fall positions from the first camera
    frame.
    """

    lmt_initial_population = {("g", 0)}

    lmt_sequence = [
        *_slice_launch_prefix(),
        *build_dual_mach_zehnder(),
    ]

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


class DeclarativeLMTSingleInterferometerFrag(
    DeclarativeLMTBase,
    NormalisedFastKineticsLMTCorrectedMixin,
    EMGainMixin,
    LoadSingleXODTMixin,
    XODTSingleMolassesPlusDipoleRampMixin,
    OpticalPumpingWithFieldSettingDipoleTrapMixin,
    FieldOnlyRampInEvapMixin,
    DipoleTrapWithExperimentBase,
):
    """
    D5: launch, then a single LMT Mach-Zehnder with ``N_BS``-recoil arms.

    Replaces the D3 single ``pi2``/``pi``/``pi2`` with the laddered
    beamsplitter/mirror/recombiner of :func:`build_single_lmt_interferometer`:
    one arm is walked out ``N_BS`` recoils and back over the dark times while
    the other parks, closing to the same two ports as D3
    (``{(e, M_TOP), (g, M_TOP + 1)}``) but with a wider enclosed area (finer
    fringe spacing). ``N_BS`` is an easily-raised module constant; ``N_BS == 1``
    is exactly the D3 Mach-Zehnder.
    """

    lmt_initial_population = {("g", 0)}

    lmt_sequence = [
        *_slice_launch_prefix(),
        *build_single_lmt_interferometer(N_BS, m_top=M_TOP),
    ]

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


DeclarativeLMTDualMachZehnder = make_fragment_scan_exp(
    DeclarativeLMTDualMachZehnderFrag
)
DeclarativeLMTSingleInterferometer = make_fragment_scan_exp(
    DeclarativeLMTSingleInterferometerFrag
)
