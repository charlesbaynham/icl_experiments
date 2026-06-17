"""
Dual (gradiometer) LMT interferometer driven by the declarative sequence
language (deliverable D6).

This is the declarative translation of the legacy double-launch double
Mach-Zehnder / :class:`LMTSymmetricInterferometryMixin` (reference run
RID 74397): a single dipole-trap cloud is launched up the momentum ladder to
``M_TOP``, a splitting pi/2 makes two momentum classes, and a wide-arm LMT
interferometer (``N_BS`` recoils per beam splitter) is run on BOTH momentum
classes sharing a common, time-symmetric mirror pulse. The two
interferometers' phases subtract, giving a gradiometer; the readout is the
differential imbalance between the two output-port pairs.

The base/mixin stack and the ``DMA_initialization_hook`` /
``post_sequence_cleanup_hook`` are copied verbatim from
:class:`~repository.LMT.lmt_declarative.DeclarativeLMTMachZehnderFrag` (D3) so
the genuine dipole-trap pathway is exercised. The wide-arm interferometer
geometry mirrors Agent-B's verified single-interferometer D5
(``DeclarativeLMTSingleInterferometerFrag``) on each momentum class.
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

# Number of launch pulses; the velocity-selective pulse provides the first
# kick, so the launch ladder runs from m = 1 and ends at m = 1 + N_LAUNCH.
N_LAUNCH = 12
M_TOP = 1 + N_LAUNCH

# Recoils opened per beam splitter (LMT depth). Start small (N_BS=2) to
# confirm closure and fringes, then scale up as contrast/time allow.
N_BS = 2


class DeclarativeLMTDualInterferometerFrag(
    DeclarativeLMTBase,
    # Repositions the camera ROIs along the ballistic trajectory predicted
    # from the recorded pulse sequence (t=0 at the dipole-trap drop). NB: do
    # not also mix in a static-config imaging mixin - it would win
    # get_andor_camera_config_hook in the MRO and install a config without
    # calculate_atom_positions.
    NormalisedFastKineticsLMTCorrectedMixin,
    EMGainMixin,
    LoadSingleXODTMixin,
    XODTSingleMolassesPlusDipoleRampMixin,
    OpticalPumpingWithFieldSettingDipoleTrapMixin,
    FieldOnlyRampInEvapMixin,
    DipoleTrapWithExperimentBase,
):
    """Launch, split and a dual (gradiometer) LMT interferometer."""

    # Atoms are released from the trap in the ground state with no kicks
    lmt_initial_population = {("g", 0)}

    # NOTE (placeholder): the interferometer span below is pending Agent-B's
    # verified D5 wide-arm geometry and Charles's decision on the D6 readout.
    # Currently this declares only the velocity slice, launch and the
    # splitting pi/2 (all verified to compile/close); the dual wide-arm
    # interferometer block is added once B's D5 arm is confirmed.
    lmt_sequence = [
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
        *ladder(start_m=1, n=N_LAUNCH, first_beam=Beam.DOWN),
        Clearout(),
        # Splitting pi/2: makes two momentum classes from |e, M_TOP>.
        pi2(Beam.DOWN, m=M_TOP, state="e", label="split"),
        # TODO(D6): dual wide-arm LMT interferometer about a common mirror,
        # mirroring Agent-B's verified D5 arm on each momentum class.
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


DeclarativeLMTDualInterferometer = make_fragment_scan_exp(
    DeclarativeLMTDualInterferometerFrag
)
