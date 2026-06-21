"""
Single-cloud double launch driven by the declarative LMT sequence language.

Validates that the declarative stack (:mod:`repository.lib.lmt_sequence` +
:class:`~repository.lib.experiment_templates.mixins.declarative_lmt.DeclarativeLMTBase`)
can express a two-arm interferometer whose arms are launched to adjacent
momentum orders, with no changes to the compiler or execution engine - the
whole sequence is a single declared pulse list.

The structure mirrors the legacy double-cloud launch
(``LMTLaunchDoubleTrapShapedPulseMixin.launch_hook_double_cloud``) but for one
physical cloud whose wavepacket the opening pi/2 splits into two arms:

1. velocity slice to a narrow class, then a pi/2 splitting ``|e, 1>`` into the
   two arms ``|g, 0>`` and ``|e, 1>``;
2. launch the excited arm up the ladder to order ``N_TOP``;
3. a dark time;
4. launch the ground arm to order ``N_TOP - 1``;
5. a final pi/2 on the ``|., N_TOP - 1> <-> |., N_TOP>`` pair to recombine the
   arms;
6. a 461 clearout of the ground port;
7. fast-kinetics readout of the excited port at the trajectory-predicted ROI.

The two arms sit at different momentum classes throughout, so every launch
pulse addresses one arm on resonance while the other is Doppler-detuned away -
exactly what the per-pulse OPLL firing path is built for. Continuous OPLL is
NOT usable here: the sequence spans many transitions.
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

# Top momentum order reached by the leading (excited) arm; the trailing
# (ground) arm is launched to N_TOP - 1, and the recombiner mixes the two.
# Modest order so both arms stay in the fast-kinetics imaging window.
N_TOP = 6

# Dark time between the two launches.
BETWEEN_LAUNCH_WAIT = 0.5e-3


def _full_intensity_setpoint() -> SetPoint:
    return SetPoint(
        setpoint=CLOCK_BEAM_DELIVERY_INFO.setpoint,
        rabi_up=1 / (2 * constants.CLOCK_PI_TIME),
        rabi_down=1 / (2 * constants.DOWN_CLOCK_BEAM_PI_TIME),
    )


def _double_launch_sequence(n_top: int, clear_ground_port: bool = True) -> list:
    """Declare the single-cloud double-launch interferometer.

    After the slice, ``|e, 1>`` is the only populated class. The opening pi/2
    splits it into the arms ``|g, 0>`` (trailing) and ``|e, 1>`` (leading).
    The leading arm climbs to ``n_top`` while the trailing arm waits at 0; then
    the trailing arm climbs to ``n_top - 1``. Parity of ``n_top`` fixes the
    recombiner beam: the two arms end as a single ``g <-> e`` pair one recoil
    apart, addressable by an UP pi/2 when ``n_top`` is odd and a DOWN pi/2 when
    it is even.

    With ``clear_ground_port`` the closing 461 clearout removes the ground port
    so the FK readout images the excited port (the recipe). Without it the
    ground port survives and is imaged directly in FK frame 0 - the diagnostic
    that shows the launch landed atoms at the predicted order without relying on
    the excited-state de-shelve.
    """
    recombiner_beam = Beam.UP if n_top % 2 == 1 else Beam.DOWN
    sequence = [
        SetPoint(
            setpoint=constants.CLOCK_SHELVING_PULSE_SETPOINT,
            rabi_up=1 / (2 * constants.CLOCK_SHELVING_PULSE_TIME),
            label="slice",
        ),
        pi(Beam.UP, m=0, label="slice"),
        _full_intensity_setpoint(),
        Clearout(),
        pi2(Beam.UP, m=1, label="bs1"),
        *ladder(start_m=1, n=n_top - 1, first_beam=Beam.DOWN),
        Wait(t=BETWEEN_LAUNCH_WAIT, label="between"),
        *ladder(start_m=0, n=n_top - 1, first_beam=Beam.UP),
        pi2(recombiner_beam, m=n_top, label="bs2"),
    ]
    if clear_ground_port:
        sequence.append(Clearout())
    return sequence


class DeclarativeDoubleLaunchFrag(
    DeclarativeLMTBase,
    NormalisedFastKineticsLMTCorrectedMixin,
    EMGainMixin,
    LoadSingleXODTMixin,
    XODTSingleMolassesPlusDipoleRampMixin,
    OpticalPumpingWithFieldSettingDipoleTrapMixin,
    FieldOnlyRampInEvapMixin,
    DipoleTrapWithExperimentBase,
):
    """Single-cloud, two-arm double launch from a declared pulse sequence."""

    lmt_initial_population = {("g", 0)}
    lmt_sequence = _double_launch_sequence(N_TOP)

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


class DeclarativeDoubleLaunchGroundReadoutFrag(DeclarativeDoubleLaunchFrag):
    """Double launch read out on the ground port (no closing clearout).

    Diagnostic twin of :class:`DeclarativeDoubleLaunchFrag`: it skips the final
    ground clearout so the launched ground arm at order ``N_TOP - 1`` survives
    into FK frame 0, making the launch visible without the (currently
    unreliable) excited-state de-shelve.
    """

    lmt_sequence = _double_launch_sequence(N_TOP, clear_ground_port=False)


DeclarativeDoubleLaunch = make_fragment_scan_exp(DeclarativeDoubleLaunchFrag)
DeclarativeDoubleLaunchGroundReadout = make_fragment_scan_exp(
    DeclarativeDoubleLaunchGroundReadoutFrag
)
