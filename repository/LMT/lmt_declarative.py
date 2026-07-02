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
from repository.lib.experiment_templates.mixins.XODT_loading import LoadSingleXODTMixin
from repository.lib.experiment_templates.mixins.XODT_molasses import (
    XODTSingleMolassesPlusDipoleRampMixin,
)
from repository.lib.lmt_sequence import Arm
from repository.lib.lmt_sequence import Beam
from repository.lib.lmt_sequence import Clearout
from repository.lib.lmt_sequence import Phase
from repository.lib.lmt_sequence import SetPoint
from repository.lib.lmt_sequence import Wait
from repository.lib.lmt_sequence import ladder
from repository.lib.lmt_sequence import pi
from repository.lib.lmt_sequence import pi2
from repository.lib.lmt_sequence import zigzag
from repository.lib.physics.lmt_resonance import EXCITED
from repository.lib.physics.lmt_resonance import GROUND

CLOCK_BEAM_DELIVERY_INFO = constants.SUSERVOED_BEAMS["clock_delivery"]
LMT_INTERFEROMETER_TIME = 100e-6  # seconds
# Number of launch pulses; the velocity-selective pulse provides the first
# kick, so the launch ladder runs from m = 1 and ends at m = 1 + N_LAUNCH.
# 8 is the 2026-07-01 working point for the single-MZ interferometer.
N_LAUNCH = 8
M_TOP = 1 + N_LAUNCH

N_LMT = 2

# Post-ladder drop time: at higher launch the cloud leaves the fixed
# fast-kinetics window; this Wait lets it fall back in before imaging.
# Image-driven - grow with n. Scannable via the spawned droptime duration.
DROP = 100e-6


class DeclarativeLMTSymmetricMachZehnderFrag(
    DeclarativeLMTBase,
    # Repositions the camera ROIs along the ballistic trajectory predicted
    # from the recorded pulse sequence, with t=0 at the dipole-trap drop
    # recorded by DeclarativeLMTBase. NB: do not also mix in one of the
    # static-config imaging mixins (e.g. NormalisedDipoleTrapFastKineticsMixin)
    # - it would win get_andor_camera_config_hook in the MRO and install a
    # config without calculate_atom_positions.
    NormalisedFastKineticsLMTCorrectedMixin,
    EMGainMixin,
    LoadSingleXODTMixin,
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
        Clearout(),
        # Launch: alternating pi pulses walking the atoms up the momentum
        # ladder from |e, 1> to m = M_TOP
        *ladder(start_m=1, n=N_LAUNCH, first_beam=Beam.DOWN, clearout_from=-4),
        Clearout(),
        Wait(t=DROP, label="droptime"),
        # Symmetric Mach-Zehnder at the top of the launch (2026-07-01 working
        # point). bs1 fixes the phase reference; mirror and bs2 share the
        # scannable interferometer_phase (in turns). Both dark times read the
        # shared lmt_dark_time handle, so one scan axis moves both together and
        # the interferometer stays symmetric about the mirror.
        Phase(phase=0.0, label="bs1"),
        pi2(Beam.UP, m=M_TOP, label="bs1"),
        Wait(param="lmt_dark_time", label="T"),
        Phase(param="interferometer_phase", label="mirror"),
        pi(Beam.UP, m=M_TOP, label="mirror"),
        Wait(param="lmt_dark_time", label="T"),
        Phase(param="interferometer_phase", label="bs2"),
        pi2(Beam.UP, m=M_TOP, label="bs2"),
    ]

    def build_fragment(self):
        super().build_fragment()

        self.setattr_param(
            "interferometer_phase", FloatParam, "Interferometer phase", default=0.0
        )
        self.interferometer_phase: FloatParamHandle

        self.setattr_param(
            "lmt_dark_time",
            FloatParam,
            "Mach-Zehnder dark time (each half)",
            default=LMT_INTERFEROMETER_TIME,
            unit="us",
            min=0.0,
        )
        self.lmt_dark_time: FloatParamHandle

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


DeclarativeLMTSymmetricMachZehnder = make_fragment_scan_exp(
    DeclarativeLMTSymmetricMachZehnderFrag, max_rtio_underflow_retries=0
)

# Zigzag ladder: the sequence structure (pulse count, turn points) is baked at
# build time - it fixes how many per-pulse parameters are spawned and the
# kernel array sizes - so these are module constants, NOT runtime parameters.
# The EFFECTIVE pulse count is set at submit time with skip_after (index map in
# the class docstrings); only a different M_TURN needs a code change, hence the
# two baked classes below.
N_ZIGZAG = 100
M_TURN = 14

N_ZIGZAG_BRINGUP = 12
M_TURN_BRINGUP = 4


def _zigzag_sequence(n: int, m_turn: int) -> list:
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
        # The slice leaves (e, 1); no clearouts inside the zigzag - the packet
        # alternates g/e every pulse, so a mid-sequence clearout would kill it
        # on half the skip_after truncations.
        *zigzag(n=n, m_turn=m_turn, start=Arm(EXCITED, 1)),
    ]


class _ZigzagLadderBase(
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
    Zigzag LMT ladder: pi pulses walking the packet up to a turning point and
    back down repeatedly, keeping the cloud in the imaging window for
    arbitrarily long pulse trains. Launch-only diagnostic - no interferometer.

    Flat event indices: 0 = slice SetPoint, 1 = slice pulse, 2 = full SetPoint,
    3 = Clearout, 4+k = zigzag pulse k. skip_after = 3 + n runs the first n
    zigzag pulses; the broad clock imaging pulse resolves the resulting
    momentum class via imaging_clock_pulse_detuning.
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


class DeclarativeLMTZigzagLadderFrag(_ZigzagLadderBase):
    """
    Zigzag ladder for the scaling campaign: N_ZIGZAG = 100 pulses baked,
    turning at M_TURN = 14. Set the effective pulse count at submit time with
    skip_after - no recompile per rung.
    """

    lmt_sequence = _zigzag_sequence(N_ZIGZAG, M_TURN)


class DeclarativeLMTZigzagBringupFrag(_ZigzagLadderBase):
    """
    Bring-up zigzag: 12 pulses turning at m = 4, so both turn types (top at
    pulse 3, bottom at pulse 6) sit inside the readout-proven range for the
    first on-atom walk.
    """

    lmt_sequence = _zigzag_sequence(N_ZIGZAG_BRINGUP, M_TURN_BRINGUP)


DeclarativeLMTZigzagLadder = make_fragment_scan_exp(
    DeclarativeLMTZigzagLadderFrag, max_rtio_underflow_retries=0
)

DeclarativeLMTZigzagBringup = make_fragment_scan_exp(
    DeclarativeLMTZigzagBringupFrag, max_rtio_underflow_retries=0
)
