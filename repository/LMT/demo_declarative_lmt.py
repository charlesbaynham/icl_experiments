"""
Minimal worked example of a declarative-LMT launch with the repumped readout.

Loads the dipole trap, velocity-slices a class into the excited clock state,
clears the unselected ground atoms, and launches the selected class n=2 recoils
up the momentum ladder. The launch ends excited (|e, 3>), so it is imaged via
the 679/707 repump - atoms in |e> are dark to 461 fast-kinetics imaging.

Runs with defaults, no submit overrides. For a clean readout on a real rig you
still tune the ROI anchor (trap_x_pixel / trap_y_pixel) and each pulse's
frequency offset (p0N_..._offset); those are calibrations, not needed to run.
"""

import logging

from artiq.language import kernel
from ndscan.experiment.entry_point import make_fragment_scan_exp

from repository.lib import constants
from repository.lib.experiment_templates.dipole_trap_experiment import (
    DipoleTrapWithExperimentBase,
)
from repository.lib.experiment_templates.mixins.andor_imaging.em_gain import EMGainMixin
from repository.lib.experiment_templates.mixins.andor_imaging.lmt_compensated_normalised_imaging import (  # noqa: E501
    DynamicROIImagingMixin,
)
from repository.lib.experiment_templates.mixins.andor_imaging.normalised_fast_kinetics_base import (  # noqa: E501
    NormalisedFastKineticsRepumpedMixin,
)
from repository.lib.experiment_templates.mixins.declarative_lmt import (
    DeclarativeLMTBase,
)
from repository.lib.experiment_templates.mixins.evaporation_mixin import (
    FieldOnlyRampInEvapMixin,
)
from repository.lib.experiment_templates.mixins.flir_blue_mot_measurement import (
    FLIRBlueMOTMeasurementMixin,
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
from repository.lib.lmt_sequence import ladder
from repository.lib.lmt_sequence import pi

logger = logging.getLogger(__name__)

CLOCK_BEAM_DELIVERY_INFO = constants.SUSERVOED_BEAMS["clock_delivery"]

# Even, so the launch ends excited and exercises the repumped readout.
_DEMO_LAUNCH_RECOILS = 2

# A launch needs a longer time-of-flight than the inherited 2 ms default, which
# aborts (the post-release launch sequence outlasts it).
_DEMO_IMAGE_TOF = 4.7e-3


class DynamicROIRepumpedImagingMixin(
    NormalisedFastKineticsRepumpedMixin, DynamicROIImagingMixin
):
    """Dynamic-ROI imaging with the 679/707 repump readout.

    The repump mixin wins ``do_first_pulse`` (ground frame, then repumpers on)
    while ``DynamicROIImagingMixin`` keeps the ROI-prediction hooks. Atoms ending
    in |e> are dark to 461 imaging and must be repumped first, so a host fragment
    must also provide ``blue_3d_mot`` via :class:`FLIRBlueMOTMeasurementMixin`.
    """


class DemoDeclarativeLMTFrag(
    DeclarativeLMTBase,
    DynamicROIRepumpedImagingMixin,
    EMGainMixin,
    FLIRBlueMOTMeasurementMixin,
    LoadSingleXODTMixin,
    XODTSingleMolassesPlusDipoleRampMixin,
    OpticalPumpingWithFieldSettingDipoleTrapMixin,
    FieldOnlyRampInEvapMixin,
    DipoleTrapWithExperimentBase,
):
    """A minimal declarative-LMT launch with the repumped fast-kinetics readout."""

    lmt_initial_population = {("g", 0)}

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
        Clearout(),  # clears the unselected atoms, still in |g>
        *ladder(start_m=1, n=_DEMO_LAUNCH_RECOILS, first_beam=Beam.DOWN),
        Clearout(),  # clears |g> residual from imperfect pulses (launch is in |e>)
    ]

    def build_fragment(self):
        super().build_fragment()
        # image_tof's inherited 2 ms default aborts a launch; re-default it so the
        # experiment runs with no overrides. EM gain already defaults on.
        self.override_param("image_tof", _DEMO_IMAGE_TOF)

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


DemoDeclarativeLMT = make_fragment_scan_exp(DemoDeclarativeLMTFrag)
