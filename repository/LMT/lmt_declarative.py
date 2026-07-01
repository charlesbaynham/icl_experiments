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
from repository.lib.physics.lmt_resonance import GROUND

CLOCK_BEAM_DELIVERY_INFO = constants.SUSERVOED_BEAMS["clock_delivery"]

# Number of launch pulses; the velocity-selective pulse provides the first
# kick, so the launch ladder runs from m = 1 and ends at m = 1 + N_LAUNCH.
N_LAUNCH = 7
M_TOP = 1 + N_LAUNCH

# Post-ladder drop time: at higher launch the cloud leaves the fixed
# fast-kinetics window; this Wait lets it fall back in before imaging.
# Image-driven - grow with n. Scannable via the spawned droptime duration.
DROP = 5e-3


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
        # # Launch: alternating pi pulses walking the atoms up the momentum
        # # ladder from |e, 1> to m = M_TOP
        *ladder(start_m=1, n=N_LAUNCH, first_beam=Beam.DOWN),
        # Clearout(),  # odd n -> ends in |g>; clearout would destroy the signal
        Wait(t=DROP, label="droptime"),
        # 10x longer:
        # SetPoint(
        #     setpoint=CLOCK_BEAM_DELIVERY_INFO.setpoint / 10**2,
        #     rabi_up=1 / (2 * constants.CLOCK_PI_TIME * 10),
        #     rabi_down=1 / (2 * constants.DOWN_CLOCK_BEAM_PI_TIME * 10),
        # ),
        # Wait(t=1e-3, label="droptime"),
        # pi(Beam.DOWN, m=1, label="spectroscopy"),
        # Mach-Zehnder on the pair |e, M_TOP> <-> |g, M_TOP + 1>.
        #
        # GOTCHA: the interferometer must be symmetric about the mirror
        # pulse or it will not close. SetPoint events cost time (servo
        # write + clock_delivery_preempt_time settle), so keep them outside
        # the interferometer as done here - or, if one is needed inside
        # (e.g. for a selective pulse on one arm), balance it with a
        # mirrored SetPoint at the corresponding position on the other side
        # of the mirror (re-declaring the current value costs exactly the
        # same time).
        # FIXME
        # pi2(Beam.DOWN, m=M_TOP, label="bs1"),
        # Wait(t=1e-3, label="dark1"),
        # pi(Beam.DOWN, m=M_TOP, label="mirror"),
        # Wait(t=1e-3, label="dark2"),
        # pi2(Beam.DOWN, m=M_TOP, label="bs2"),
        # Escape-hatch example (v2): a shaped pulse implemented by an
        # overridden lmt_sequence_callback_hook, declaring its momentum effect
        # as a list of addressed actions so the bookkeeping of later pulses
        # stays correct:
        # Callback(callback_id=1, actions=[
        #     CallbackAction(state=EXCITED, m=M_TOP, delta_m=1),  # FLIP by default
        # ]),
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


DeclarativeLMTSymmetricMachZehnder = make_fragment_scan_exp(
    DeclarativeLMTSymmetricMachZehnderFrag, max_rtio_underflow_retries=0
)
