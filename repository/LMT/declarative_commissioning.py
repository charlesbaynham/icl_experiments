"""
Commissioning experiments for the declarative LMT stack (dipole-trap base).

Two minimal experiments used to validate the genuine dipole-trap pathway of the
declarative LMT framework (:mod:`repository.lib.lmt_sequence` +
:class:`~repository.lib.experiment_templates.mixins.declarative_lmt.DeclarativeLMTBase`)
on atoms, before running the full launch + interferometer of
:class:`~repository.LMT.lmt_declarative.DeclarativeLMTMachZehnderFrag`:

* :class:`DeclarativeLMTSinglePulseFrag` (D1) - one full-intensity resonant pi
  pulse on the released ground-state cloud, no slice/launch/interferometer.
* :class:`DeclarativeLMTSlicedSpecFrag` (D2) - velocity slice -> full intensity
  -> clearout -> spectroscopy pulse.

Both reuse the exact base/mixin stack and both hooks of
``DeclarativeLMTMachZehnderFrag``.
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
from repository.lib.lmt_sequence import pi

CLOCK_BEAM_DELIVERY_INFO = constants.SUSERVOED_BEAMS["clock_delivery"]


class DeclarativeLMTSinglePulseFrag(
    DeclarativeLMTBase,
    NormalisedFastKineticsLMTCorrectedMixin,
    EMGainMixin,
    LoadSingleXODTMixin,
    XODTSingleMolassesPlusDipoleRampMixin,
    OpticalPumpingWithFieldSettingDipoleTrapMixin,
    FieldOnlyRampInEvapMixin,
    DipoleTrapWithExperimentBase,
):
    """D1: a single full-intensity resonant pi pulse on the released cloud.

    Smoke test of the genuine dipole pathway: trap load -> drop -> declarative
    engine -> FK de-shelve readout, with no slice/launch/interferometer.
    """

    # Atoms are released from the trap in the ground state with no kicks
    lmt_initial_population = {("g", 0)}

    lmt_sequence = [
        # Full intensity; the declared Rabi frequencies set the default pulse
        # durations (pi time = 1 / (2 * Rabi)).
        SetPoint(
            setpoint=CLOCK_BEAM_DELIVERY_INFO.setpoint,
            rabi_up=1 / (2 * constants.CLOCK_PI_TIME),
            rabi_down=1 / (2 * constants.DOWN_CLOCK_BEAM_PI_TIME),
        ),
        pi(Beam.UP, m=0, label="spec"),
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


DeclarativeLMTSinglePulse = make_fragment_scan_exp(DeclarativeLMTSinglePulseFrag)


class DeclarativeLMTSlicedSpecFrag(
    DeclarativeLMTBase,
    NormalisedFastKineticsLMTCorrectedMixin,
    EMGainMixin,
    LoadSingleXODTMixin,
    XODTSingleMolassesPlusDipoleRampMixin,
    OpticalPumpingWithFieldSettingDipoleTrapMixin,
    FieldOnlyRampInEvapMixin,
    DipoleTrapWithExperimentBase,
):
    """D2: velocity slice -> full intensity -> clearout -> spectroscopy pulse.

    The real slice->full->clearout->spec sequence on the genuine dipole base
    (the same body as the red-MOT sliced-spec hack, but on
    :class:`DeclarativeLMTBase`).
    """

    # Atoms are released from the trap in the ground state with no kicks
    lmt_initial_population = {("g", 0)}

    lmt_sequence = [
        # Velocity selection: a longer, lower-intensity pulse. The set point
        # (p00_setpoint_slice) should be calibrated on atoms.
        SetPoint(
            setpoint=constants.CLOCK_SHELVING_PULSE_SETPOINT,
            rabi_up=1 / (2 * constants.CLOCK_SHELVING_PULSE_TIME),
            label="slice",
        ),
        pi(Beam.UP, m=0, label="slice"),
        # Full intensity for the spectroscopy pulse.
        SetPoint(
            setpoint=CLOCK_BEAM_DELIVERY_INFO.setpoint,
            rabi_up=1 / (2 * constants.CLOCK_PI_TIME),
            rabi_down=1 / (2 * constants.DOWN_CLOCK_BEAM_PI_TIME),
        ),
        # Blast away the unselected ground-state atoms.
        Clearout(),
        pi(Beam.UP, m=1, label="spec"),
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


DeclarativeLMTSlicedSpec = make_fragment_scan_exp(DeclarativeLMTSlicedSpecFrag)
