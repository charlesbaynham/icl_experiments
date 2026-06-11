"""
LMT interferometry driven by the declarative sequence language.

This is the reference experiment for the declarative LMT stack
(:mod:`repository.lib.lmt_sequence` +
:class:`~repository.lib.experiment_templates.mixins.declarative_lmt.DeclarativeLMTBase`):
the launch and a Mach-Zehnder interferometer are declared as a single list of
pulse descriptions, from which scannable per-pulse parameters (detuning
offsets and durations) are generated with model-predicted defaults.
"""

from artiq.language import kernel
from ndscan.experiment.entry_point import make_fragment_scan_exp

from repository.lib import constants
from repository.lib.experiment_templates.dipole_trap_experiment import (
    DipoleTrapWithExperimentBase,
)
from repository.lib.experiment_templates.mixins.andor_imaging.em_gain import EMGainMixin
from repository.lib.experiment_templates.mixins.andor_imaging.normalised_fast_kinetics import (
    NormalisedDipoleTrapFastKineticsMixin,
)
from repository.lib.experiment_templates.mixins.andor_imaging.normalised_fast_kinetics_base import (
    NormalisedFastKineticsClockPulseMixin,
)
from repository.lib.experiment_templates.mixins.clock_shelving import (
    ClockShelvingAndClearoutDipoleTrapMixin,
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

# Number of launch pulses; the shelving pulse provides the first kick, so the
# atoms start the sequence at |e, 1> and the launch ladder ends at
# m = 1 + N_LAUNCH.
N_LAUNCH = 12
M_TOP = 1 + N_LAUNCH


class DeclarativeLMTMachZehnderFrag(
    DeclarativeLMTBase,
    NormalisedDipoleTrapFastKineticsMixin,
    NormalisedFastKineticsClockPulseMixin,
    EMGainMixin,
    LoadSingleXODTMixin,
    XODTSingleMolassesPlusDipoleRampMixin,
    OpticalPumpingWithFieldSettingDipoleTrapMixin,
    FieldOnlyRampInEvapMixin,
    ClockShelvingAndClearoutDipoleTrapMixin,
    DipoleTrapWithExperimentBase,
):
    """
    Launch plus Mach-Zehnder interferometer from a declared pulse sequence
    """

    # After the shelving kick the atoms are excited with one recoil
    lmt_initial_population = {("e", 1)}

    lmt_sequence = [
        # Per-beam delivery set points; the declared Rabi frequencies set the
        # default pulse durations (pi time = 1 / (2 * Rabi))
        SetPoint(
            Beam.UP,
            setpoint=CLOCK_BEAM_DELIVERY_INFO.setpoint,
            rabi_frequency=1 / (2 * constants.CLOCK_PI_TIME),
        ),
        SetPoint(
            Beam.DOWN,
            setpoint=CLOCK_BEAM_DELIVERY_INFO.setpoint,
            rabi_frequency=1 / (2 * constants.DOWN_CLOCK_BEAM_PI_TIME),
        ),
        # Launch: alternating pi pulses walking the atoms up the momentum
        # ladder from |e, 1> to m = M_TOP
        *ladder(start_m=1, n=N_LAUNCH, first_beam=Beam.DOWN),
        # Remove any ground-state population left behind by imperfect pulses
        Clearout(),
        # Mach-Zehnder on the pair |e, M_TOP> <-> |g, M_TOP + 1>
        pi2(Beam.DOWN, m=M_TOP, label="bs1"),
        Wait(t=1e-3, label="dark1"),
        pi(Beam.DOWN, m=M_TOP, label="mirror"),
        Wait(t=1e-3, label="dark2"),
        pi2(Beam.DOWN, m=M_TOP, label="bs2"),
        # Escape-hatch example (v2): a shaped pulse implemented by an
        # overridden lmt_sequence_callback, declaring its momentum effect so
        # the bookkeeping of later pulses stays correct:
        # Callback(callback_id=1, delta_m=1, state_effect="flip"),
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
        self.post_sequence_cleanup_hook_shelving()
        self.post_sequence_cleanup_hook_declarative_lmt()


DeclarativeLMTMachZehnder = make_fragment_scan_exp(DeclarativeLMTMachZehnderFrag)
