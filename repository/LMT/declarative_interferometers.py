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


class DeclarativeLMTDualMachZehnderFrag(
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
    D4: launch, split into two clouds, then a dual Mach-Zehnder.

    After the launch the cloud is excited at ``M_TOP``. A splitting ``pi2``
    (``split``) makes two clouds at adjacent momentum classes: ``(e, M_TOP)``
    and ``(g, M_TOP + 1)``. A momentum-selective ``pi2`` then opens an
    independent Mach-Zehnder on *each* cloud (``bs1_lo`` / ``bs1_hi``), a shared
    pair of pi pulses mirrors both (``mir_lo`` / ``mir_hi``), and a final pair
    of ``pi2`` pulses recombines both (``bs2_lo`` / ``bs2_hi``). Every
    interferometer pulse carries ``state=`` because the split leaves both
    internal states populated at neighbouring m.

    The two interferometers close to four distinct ports:
    ``{(g, M_TOP - 1), (e, M_TOP)}`` (lower) and
    ``{(g, M_TOP + 1), (e, M_TOP + 2)}`` (upper); the readout is the imbalance
    between the two ports of each. No SetPoint/Clearout falls between the first
    and last beam splitters and the two dark times are symmetric about the
    mirror, so both interferometers satisfy the closure constraint.
    """

    lmt_initial_population = {("g", 0)}

    lmt_sequence = [
        *_slice_launch_prefix(),
        # Splitting pi/2: makes two clouds {(e, M_TOP), (g, M_TOP + 1)}.
        pi2(Beam.DOWN, m=M_TOP, label="split"),
        # First beam splitter of each interferometer (momentum-selective).
        #   lower cloud (e, M_TOP)     -> pair (g, M_TOP - 1) <-> (e, M_TOP)
        #   upper cloud (g, M_TOP + 1) -> pair (g, M_TOP + 1) <-> (e, M_TOP + 2)
        pi2(Beam.UP, m=M_TOP, state="e", label="bs1_lo"),
        pi2(Beam.UP, m=M_TOP + 1, state="g", label="bs1_hi"),
        Wait(t=1e-3, label="dark1"),
        # Mirror each pair (swaps the populations of each interferometer).
        pi(Beam.UP, m=M_TOP, label="mir_lo"),
        pi(Beam.UP, m=M_TOP + 1, label="mir_hi"),
        Wait(t=1e-3, label="dark2"),
        # Recombiner of each interferometer.
        pi2(Beam.UP, m=M_TOP, label="bs2_lo"),
        pi2(Beam.UP, m=M_TOP + 1, label="bs2_hi"),
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
