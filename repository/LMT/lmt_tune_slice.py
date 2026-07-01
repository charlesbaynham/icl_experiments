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
from repository.lib.lmt_sequence import pi
from repository.lib.physics.lmt_resonance import GROUND

CLOCK_BEAM_DELIVERY_INFO = constants.SUSERVOED_BEAMS["clock_delivery"]


class NarrowDownAfterSliceFrag(
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
    Narrow down after slice

    Designed for tuning the SUServo offset to select v=0 atoms
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
        # Reduced intensity for a down pulse, to intentionally make it more
        # sensitive to incorrect velocity class selection
        Clearout(),
        SetPoint(
            setpoint=CLOCK_BEAM_DELIVERY_INFO.setpoint / 100,
            rabi_up=1 / (2 * constants.CLOCK_PI_TIME * 10),
            rabi_down=1 / (2 * constants.DOWN_CLOCK_BEAM_PI_TIME * 10),
        ),
        pi(Beam.DOWN, m=1, label="down_spec"),
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


NarrowDownAfterSlice = make_fragment_scan_exp(
    NarrowDownAfterSliceFrag, max_rtio_underflow_retries=0
)
