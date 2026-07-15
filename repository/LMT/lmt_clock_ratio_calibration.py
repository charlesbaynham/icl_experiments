"""
Clock Rabi / set-point ratio calibration in the declarative LMT framework.

Re-measures the post-rebuild Rabi anchor ``(V_ref, T_ref)`` per beam: a fixed
velocity-selective slice + clearout prepares a clean velocity class, then a
single probe pulse on the *same beam* drives it coherently. Scanning the probe
duration gives a Rabi flop whose pi time is the new ``T_ref`` at the operating
delivery set point ``V_ref``. The slice and probe share a beam (and therefore a
Doppler class), unlike the normal declarative LMT sequence which slices up and
launches down.

The clock AC-Stark retake (DeclarativeClockShift{Up,Down}) consumes the
``(V_ref, T_ref)`` measured here to build its ``V_auto = V_ref*(T_ref/T)**2``
grid, so fold the fitted values back into ``constants.py`` once measured.
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
from repository.lib.physics.lmt_resonance import GROUND

CLOCK_BEAM_DELIVERY_INFO = constants.SUSERVOED_BEAMS["clock_delivery"]


def _ratio_cal_sequence(beam: Beam):
    """Fixed slice + clearout + same-beam probe, ready to Rabi-flop.

    The slice ``pi(beam, m=0)`` takes ``(g, 0) -> (e, beam.sign)``; the clearout
    blasts the unselected ground state; the probe ``pi(beam, m=beam.sign)``
    drives the selected ``(e, beam.sign) -> (g, 0)``. Scan the probe duration
    (``p04_pi_probe_duration``) for the flop.
    """
    slice_rabi = 1 / (2 * constants.CLOCK_SHELVING_PULSE_TIME)
    probe_pi_time = (
        constants.CLOCK_PI_TIME
        if beam is Beam.UP
        else constants.DOWN_CLOCK_BEAM_PI_TIME
    )
    probe_rabi = 1 / (2 * probe_pi_time)

    return [
        SetPoint(
            setpoint=constants.CLOCK_SHELVING_PULSE_SETPOINT,
            rabi_up=slice_rabi if beam is Beam.UP else None,
            rabi_down=slice_rabi if beam is Beam.DOWN else None,
            label="slice",
        ),
        pi(beam, m=0, label="slice"),
        Clearout(),
        SetPoint(
            setpoint=CLOCK_BEAM_DELIVERY_INFO.setpoint,
            rabi_up=probe_rabi if beam is Beam.UP else None,
            rabi_down=probe_rabi if beam is Beam.DOWN else None,
            label="probe",
        ),
        pi(beam, m=beam.sign, label="probe"),
    ]


class _DeclarativeClockRatioCalBase(
    DeclarativeLMTBase,
    NormalisedFastKineticsLMTCorrectedMixin,
    EMGainMixin,
    LoadSingleXODTMixin,
    XODTSingleMolassesPlusDipoleRampMixin,
    OpticalPumpingWithFieldSettingDipoleTrapMixin,
    FieldOnlyRampInEvapMixin,
    DipoleTrapWithExperimentBase,
):
    """Velocity-selected Rabi flop on the probe pulse; subclass picks the beam."""

    lmt_initial_population = {(GROUND, 0)}

    def build_fragment(self):
        super().build_fragment()
        # Raw Rabi-flop: no Stark compensation should pull the probe off
        # resonance as its duration (and hence modelled Rabi) is scanned.
        self.override_param("lmt_probe_stark_alpha", initial_value=0.0)

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


class DeclarativeClockRatioCalUpFrag(_DeclarativeClockRatioCalBase):
    """Up-beam clock Rabi/set-point ratio calibration."""

    lmt_sequence = _ratio_cal_sequence(Beam.UP)


class DeclarativeClockRatioCalDownFrag(_DeclarativeClockRatioCalBase):
    """Down-beam clock Rabi/set-point ratio calibration."""

    lmt_sequence = _ratio_cal_sequence(Beam.DOWN)


DeclarativeClockRatioCalUp = make_fragment_scan_exp(DeclarativeClockRatioCalUpFrag)
DeclarativeClockRatioCalDown = make_fragment_scan_exp(DeclarativeClockRatioCalDownFrag)
