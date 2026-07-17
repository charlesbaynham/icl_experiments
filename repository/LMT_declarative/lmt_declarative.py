"""
LMT interferometry driven by the declarative sequence language.

This is the reference experiment for the declarative LMT stack
(:mod:`repository.lib.lmt_sequence` +
:class:`~repository.lib.experiment_templates.mixins.declarative_lmt.DeclarativeLMTBase`):
the velocity-selective pulse, the launch and a symmetric Mach-Zehnder
interferometer are declared as a single list of pulse descriptions, from
which scannable per-pulse parameters (detuning offsets and durations) are
generated with model-predicted defaults.
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
from repository.lib.experiment_templates.mixins.painted_quadratic import (
    AdiabaticCoolingWithPaintedQuadraticMixin,
)
from repository.lib.experiment_templates.mixins.XODT_loading import (
    LoadSingleXODTWithPainterMixin,
)
from repository.lib.experiment_templates.mixins.XODT_molasses import (
    XODTSingleMolassesPlusDipoleRampMixin,
)
from repository.lib.lmt_sequence import Beam
from repository.lib.lmt_sequence import Clearout
from repository.lib.lmt_sequence import SetPoint
from repository.lib.lmt_sequence import Wait
from repository.lib.lmt_sequence import ladder
from repository.lib.lmt_sequence import pi
from repository.lib.physics.lmt_resonance import GROUND

CLOCK_BEAM_DELIVERY_INFO = constants.SUSERVOED_BEAMS["clock_delivery"]
LMT_INTERFEROMETER_TIME = 100e-6  # seconds
# Number of launch pulses; the velocity-selective pulse provides the first
# kick, so the launch ladder runs from m = 1 and ends at m = 1 + N_LAUNCH.
N_LAUNCH = 10
M_TOP = 1 + N_LAUNCH


N_LMT = 2

# Post-ladder drop time: at higher launch the cloud leaves the fixed
# fast-kinetics window; this Wait lets it fall back in before imaging.
# Image-driven - grow with n. Scannable via the spawned droptime duration.
DROP = 100e-6


class DeclarativeLMTSymmetricMachZehnderFrag(
    DeclarativeLMTBase,
    NormalisedFastKineticsLMTCorrectedMixin,
    EMGainMixin,
    AdiabaticCoolingWithPaintedQuadraticMixin,
    LoadSingleXODTWithPainterMixin,
    XODTSingleMolassesPlusDipoleRampMixin,
    OpticalPumpingWithFieldSettingDipoleTrapMixin,
    FieldOnlyRampInEvapMixin,
    DipoleTrapWithExperimentBase,
):
    """
    Declarative symmetric LMT interferometry
    """

    # Atoms are released from the trap in the ground state with no kicks
    lmt_initial_population = {(GROUND, 0)}

    lmt_sequence = [
        # Velocity selection
        SetPoint(
            setpoint=constants.CLOCK_SHELVING_PULSE_SETPOINT,
            rabi_up=1 / (2 * constants.CLOCK_SHELVING_PULSE_TIME),
            label="slice",
        ),
        pi(Beam.UP, m=0, label="slice"),
        # Full intensity for the launch and interferometer; the declared
        # Rabi frequencies set the default pulse durations
        # (pi time = 1 / (2 * Rabi))
        SetPoint(
            setpoint=CLOCK_BEAM_DELIVERY_INFO.setpoint,
            rabi_up=1 / (2 * constants.CLOCK_PI_TIME),
            rabi_down=1 / (2 * constants.DOWN_CLOCK_BEAM_PI_TIME),
        ),
        # Blast away the unselected ground-state atoms
        Clearout(duration=2.2e-3),
        # Launch: alternating pi pulses walking the atoms up the momentum
        # ladder from |e, 1> to m = M_TOP
        *ladder(start_m=1, n=N_LAUNCH, first_beam=Beam.DOWN, clearout_from=-1),
        Wait(t=DROP, label="droptime"),
        # # Now do some actual interferometry
        # # %% LMT beamsplitter
        # Phase(phase=0.0, label="bs1"),
        # pi2(Beam.UP, m=M_TOP, label="bs1"),
        # *ladder(start_m=M_TOP, n=N_LMT, first_beam=Beam.DOWN),
        # Wait(t=LMT_INTERFEROMETER_TIME, label="T"),
        # # %% LMT mirror
        # *ladder(
        #     start_m=M_TOP + N_LMT,
        #     n=N_LMT,
        #     direction=-1,
        #     first_beam=Beam.DOWN,
        # ),
        # Phase(param="interferometer_phase", label="mirror"),
        # Clearout(),  # FIXME test
        # pi(Beam.UP, m=M_TOP, label="mirror"),
        # FIXME
        # *ladder(start_m=M_TOP, n=N_LMT, direction=+1, first_beam=Beam.DOWN),
        # Wait(t=LMT_INTERFEROMETER_TIME, label="T"),
        # *ladder(
        #     start_m=M_TOP + N_LMT,
        #     n=N_LMT,
        #     direction=-1,
        #     first_beam=Beam.DOWN,
        # ),
        # Phase(param="interferometer_phase", label="bs2"),
        # pi2(Beam.UP, m=M_TOP, label="bs2"),
    ]

    def build_fragment(self):
        super().build_fragment()

        self.setattr_param(
            "interferometer_phase", FloatParam, "Interferometer phase", default=0.0
        )
        self.interferometer_phase: FloatParamHandle

    @kernel
    def DMA_initialization_hook(self):
        self.DMA_initialization_hook_redmot_default()
        self.DMA_initialization_hook_dipole_trap_default()
        self.DMA_initialization_hook_loading_xodt_mot()
        self.DMA_initialization_hook_xodt_molasses()
        self.DMA_initialization_hook_painter_on()
        self.DMA_initialization_hook_adiabatic_cooling()
        self.DMA_initialization_hook_evap_with_field_ramp()

    @kernel
    def post_sequence_cleanup_hook(self):
        self.post_sequence_cleanup_hook_base()
        self.post_sequence_cleanup_hook_andor()
        self.post_sequence_cleanup_hook_declarative_lmt()
        self.post_sequence_cleanup_hook_loading()


DeclarativeLMTSymmetricMachZehnder = make_fragment_scan_exp(
    DeclarativeLMTSymmetricMachZehnderFrag, max_rtio_underflow_retries=0
)
