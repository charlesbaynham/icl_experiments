"""
Minimal worked example: a declarative-LMT launch with the repumped readout.

A deliberately small, self-contained demonstration of how to drive the
declarative large-momentum-transfer (LMT) framework end to end:

* compose the dipole-trap loading stack with the declarative-LMT base and the
  dynamic-ROI **repumped** fast-kinetics readout;
* declare an LMT pulse sequence in the sequence language (a velocity slice, a
  clearout, then a launch ladder); and
* read out the launched cloud - which ends in the shelved excited clock state
  ``|e>`` - via the 679/707 repump, so the excited population is imaged.

It launches a single velocity class two recoils up the momentum ladder
(``n = 2``). Two is the smallest *even* launch, and an even launch ends in
``|e, n+1>``; ending excited is what exercises the repumped readout (an odd
launch ends in the ground state and would not need it). The experiment runs with
its defaults - no submit overrides are required.

This is a worked example of the declarative-LMT API, not a calibrated
measurement. For a clean readout on a real rig you would still tune, on the
dashboard, the trap-cloud anchor (``trap_x_pixel`` / ``trap_y_pixel``) so the
dynamic ROI lands on the launched cloud, and each pulse's frequency offset
(``p0N_..._offset``) for maximum transfer. Those are per-rig calibrations, not
needed for the experiment to run. EM gain is on by default for a usable image;
the ``DISABLE_EM_GAIN`` camera interlock dataset still guards the hardware and is
never touched here.
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

# Number of recoils in the demo launch. Even, so the launched class ends excited
# (|e, n+1>) and exercises the repumped readout.
_DEMO_LAUNCH_RECOILS = 2

# Time of flight from dipole-trap release to the first fast-kinetics frame. The
# launch's real-time hardware writes consume RTIO time after release, so the
# inherited 2 ms default would abort; ~4.7 ms clears the launch sequence and
# keeps the cloud inside the fast-kinetics imaging band.
_DEMO_IMAGE_TOF = 4.7e-3


class DynamicROIRepumpedImagingMixin(
    NormalisedFastKineticsRepumpedMixin, DynamicROIImagingMixin
):
    """
    Dynamic-ROI imaging combined with the 679/707 repump readout.

    ``NormalisedFastKineticsRepumpedMixin`` wins ``do_first_pulse`` (fire the
    ground frame, then turn on the 679/707 repumpers), while
    ``DynamicROIImagingMixin`` still wins ``before_start_hook`` /
    ``do_imaging_hook_andor`` / ``get_andor_camera_config_hook``, so the
    dynamic-ROI position prediction is preserved.

    Atoms that end shelved in the excited clock state ``|e>`` (any even-n LMT
    launch ends ``|e, n+1>``) are dark to 461 fast-kinetics imaging and must be
    repumped back onto the ground cycling transition before the second frame can
    see them. A host fragment using this mixin must therefore also provide
    ``blue_3d_mot`` (via :class:`FLIRBlueMOTMeasurementMixin`) for
    ``turn_on_repumpers``.
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
    """
    A minimal declarative-LMT launch with the repumped fast-kinetics readout.

    Loads a single crossed dipole trap, releases the cloud, velocity-slices a
    class into the excited clock state, clears the unselected ground atoms, then
    walks the selected class ``n = 2`` recoils up the momentum ladder. The
    launched class ends in ``|e, 3>``, so the repumped readout images it.

    A worked example of the declarative-LMT API, not a calibrated measurement;
    see the module docstring for the per-rig calibration (ROI anchor, per-pulse
    frequency offsets) you would tune for a clean readout.
    """

    # The cloud is released from the trap in the ground state with no kicks.
    lmt_initial_population = {("g", 0)}

    # Declarative LMT sequence:
    #   1. drop to the slice set point and velocity-slice a class into |e, 1>,
    #   2. return to full delivery intensity,
    #   3. clear the unselected |g> atoms,
    #   4. launch the selected class n recoils up the ladder (alternating beams),
    #   5. clear residual |g> left by imperfect pulses (valid for even n, which
    #      ends excited so the launched atoms survive the |g>-selective clearout).
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
        *ladder(start_m=1, n=_DEMO_LAUNCH_RECOILS, first_beam=Beam.DOWN),
        Clearout(),
    ]

    def build_fragment(self):
        super().build_fragment()
        # Re-default the inherited image_tof so the experiment runs with no
        # submit overrides: the inherited 2 ms aborts a launch (the post-release
        # launch sequence outlasts it), whereas ~4.7 ms clears the sequence and
        # keeps the cloud in the fast-kinetics band. override_param is the
        # established repo idiom for pinning an inherited parameter (see
        # DipoleTrapWithExperimentBase.override_param("expansion_time", 0)).
        # em_gain_enabled already defaults to True in EMGainMixin, so it needs no
        # override here; the DISABLE_EM_GAIN interlock still guards the camera.
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
