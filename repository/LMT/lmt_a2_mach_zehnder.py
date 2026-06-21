"""
Milestone A2: single-cloud Mach-Zehnder, built up one LMT order at a time.

Three declarative variants share the dipole-release stack and fast-kinetics
excitation-fraction readout of the reference
:class:`repository.LMT.lmt_declarative.DeclarativeLMTMachZehnderFrag`; they
differ only in how much momentum the interferometer carries:

* :class:`A2MachZehnderDropFrag` - no slice, no launch. A pi/2 - T - pi - T -
  pi/2 Mach-Zehnder straight on ``|g, 0> <-> |e, 1>`` from the trapped cloud.
  This isolates the interferometer machinery (phase readout, ROI, RTIO budget)
  from launch-transfer and velocity-slice errors - the first-fringe machine.
* :class:`A2MachZehnderSlicedFrag` - velocity slice (narrow class) then the
  same single-order MZ on the sliced ``|e, 1>``, no launch ladder.
* :class:`A2MachZehnderLaunch2Frag` - slice, two-recoil launch, then the MZ on
  the top pair ``|e, 3> <-> |g, 4>`` (the first MZ-on-a-launch).

Seeing fringes
--------------

The excitation fraction oscillates with the recombiner phase. Scan the final
pi/2's detuning offset - in a phase-continuous DDS the offset accumulates as a
linear phase, so the excitation fraction traces a sinusoid. The fringe period
in offset is ~ ``1 / T`` (the dark time); at ``T = 1 ms`` that is ~ 1 kHz. The
recombiner offset parameters are:

* drop:     ``p05_pi2_u_m0_bs2_offset``
* sliced:   ``p08_pi2_u_m1_bs2_offset``
* launch-2: ``p11_pi2_d_m3_bs2_offset``

The equal dark times (``..._wait_dark1_duration`` / ``..._dark2_duration``,
kept equal so the interferometer stays symmetric about the mirror) are an
alternative phase axis.
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
from repository.lib.lmt_sequence import SetPoint
from repository.lib.lmt_sequence import Wait
from repository.lib.lmt_sequence import ladder
from repository.lib.lmt_sequence import pi
from repository.lib.lmt_sequence import pi2

CLOCK_BEAM_DELIVERY_INFO = constants.SUSERVOED_BEAMS["clock_delivery"]

MZ_DARK_TIME = 1e-3


def _full_intensity_setpoint() -> SetPoint:
    return SetPoint(
        setpoint=CLOCK_BEAM_DELIVERY_INFO.setpoint,
        rabi_up=1 / (2 * constants.CLOCK_PI_TIME),
        rabi_down=1 / (2 * constants.DOWN_CLOCK_BEAM_PI_TIME),
    )


def _slice() -> list:
    """Velocity-selective shelving pulse: |g, 0> -> |e, 1>, lower set point."""
    return [
        SetPoint(
            setpoint=constants.CLOCK_SHELVING_PULSE_SETPOINT,
            rabi_up=1 / (2 * constants.CLOCK_SHELVING_PULSE_TIME),
            label="slice",
        ),
        pi(Beam.UP, m=0, label="slice"),
    ]


def _mach_zehnder(beam: Beam, m: int) -> list:
    """Symmetric pi/2 - dark - pi - dark - pi/2 on the addressed pair."""
    return [
        pi2(beam, m=m, label="bs1"),
        Wait(t=MZ_DARK_TIME, label="dark1"),
        pi(beam, m=m, label="mirror"),
        Wait(t=MZ_DARK_TIME, label="dark2"),
        pi2(beam, m=m, label="bs2"),
    ]


class _A2MachZehnderHooks:
    """Initialisation and cleanup hooks shared by the A2 variants.

    A plain (non-Fragment) mixin placed first in the MRO: it only overrides the
    two hooks, which call the per-mixin defaults resolved through the rest of
    the MRO. It is not itself a runnable experiment.
    """

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


class A2MachZehnderDropFrag(
    _A2MachZehnderHooks,
    DeclarativeLMTBase,
    NormalisedFastKineticsLMTCorrectedMixin,
    EMGainMixin,
    LoadSingleXODTMixin,
    XODTSingleMolassesPlusDipoleRampMixin,
    OpticalPumpingWithFieldSettingDipoleTrapMixin,
    FieldOnlyRampInEvapMixin,
    DipoleTrapWithExperimentBase,
):
    """Single-order MZ on |g, 0> <-> |e, 1> straight from the trap."""

    lmt_initial_population = {("g", 0)}
    lmt_sequence = [
        _full_intensity_setpoint(),
        *_mach_zehnder(Beam.UP, m=0),
    ]


class A2MachZehnderSlicedFrag(
    _A2MachZehnderHooks,
    DeclarativeLMTBase,
    NormalisedFastKineticsLMTCorrectedMixin,
    EMGainMixin,
    LoadSingleXODTMixin,
    XODTSingleMolassesPlusDipoleRampMixin,
    OpticalPumpingWithFieldSettingDipoleTrapMixin,
    FieldOnlyRampInEvapMixin,
    DipoleTrapWithExperimentBase,
):
    """Velocity slice, then single-order MZ on the sliced |e, 1> (no launch)."""

    lmt_initial_population = {("g", 0)}
    lmt_sequence = [
        *_slice(),
        _full_intensity_setpoint(),
        Clearout(),
        *_mach_zehnder(Beam.UP, m=1),
    ]


class A2MachZehnderLaunch2Frag(
    _A2MachZehnderHooks,
    DeclarativeLMTBase,
    NormalisedFastKineticsLMTCorrectedMixin,
    EMGainMixin,
    LoadSingleXODTMixin,
    XODTSingleMolassesPlusDipoleRampMixin,
    OpticalPumpingWithFieldSettingDipoleTrapMixin,
    FieldOnlyRampInEvapMixin,
    DipoleTrapWithExperimentBase,
):
    """Slice, two-recoil launch, then the MZ on the top pair |e, 3> <-> |g, 4>."""

    lmt_initial_population = {("g", 0)}
    lmt_sequence = [
        *_slice(),
        _full_intensity_setpoint(),
        Clearout(),
        *ladder(start_m=1, n=2, first_beam=Beam.DOWN),
        Clearout(),
        *_mach_zehnder(Beam.DOWN, m=3),
    ]


class A2RamseyFrag(
    _A2MachZehnderHooks,
    DeclarativeLMTBase,
    NormalisedFastKineticsLMTCorrectedMixin,
    EMGainMixin,
    LoadSingleXODTMixin,
    XODTSingleMolassesPlusDipoleRampMixin,
    OpticalPumpingWithFieldSettingDipoleTrapMixin,
    FieldOnlyRampInEvapMixin,
    DipoleTrapWithExperimentBase,
):
    """Ramsey (pi/2 - dark - pi/2) on |g, 0> <-> |e, 1>, no mirror, no launch.

    The minimal coherence / phase-knob test: scan the final pi/2's laser phase
    ``p03_pi2_u_m0_bs2_phase`` from 0 to 2*pi and read the ground-port fringe.
    """

    lmt_initial_population = {("g", 0)}
    lmt_sequence = [
        _full_intensity_setpoint(),
        pi2(Beam.UP, m=0, label="bs1"),
        Wait(t=MZ_DARK_TIME, label="dark"),
        pi2(Beam.UP, m=0, label="bs2"),
    ]


class A2ClockLineCentreFrag(
    _A2MachZehnderHooks,
    DeclarativeLMTBase,
    NormalisedFastKineticsLMTCorrectedMixin,
    EMGainMixin,
    LoadSingleXODTMixin,
    XODTSingleMolassesPlusDipoleRampMixin,
    OpticalPumpingWithFieldSettingDipoleTrapMixin,
    FieldOnlyRampInEvapMixin,
    DipoleTrapWithExperimentBase,
):
    """A single pi pulse on |g, 0> <-> |e, 1> (UP) from the trap.

    Carrier diagnostic for the MZ: scan ``p01_pi_u_m0_carrier_offset`` and read
    out. Resonance shows as maximal ground depletion (robust to a failing clock
    de-shelve) and, if the de-shelve readout works, peak excitation fraction.
    The offset at peak transfer is the carrier correction the MZ pulses need.
    """

    lmt_initial_population = {("g", 0)}
    lmt_sequence = [
        _full_intensity_setpoint(),
        pi(Beam.UP, m=0, label="carrier"),
    ]


A2MachZehnderDrop = make_fragment_scan_exp(A2MachZehnderDropFrag)
A2MachZehnderSliced = make_fragment_scan_exp(A2MachZehnderSlicedFrag)
A2MachZehnderLaunch2 = make_fragment_scan_exp(A2MachZehnderLaunch2Frag)
A2ClockLineCentre = make_fragment_scan_exp(A2ClockLineCentreFrag)
A2Ramsey = make_fragment_scan_exp(A2RamseyFrag)
