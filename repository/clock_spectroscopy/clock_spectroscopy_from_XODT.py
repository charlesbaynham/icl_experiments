import logging

from artiq.experiment import kernel
from ndscan.experiment.entry_point import make_fragment_scan_exp

from repository.lib.experiment_templates.dipole_trap_experiment import (
    DipoleTrapWithExperiment,
)
from repository.lib.experiment_templates.mixins.andor_imaging.double_trap_imaging import (
    DoubleTrapImagingNormalised,
)
from repository.lib.experiment_templates.mixins.clock_spectroscopy import (
    ClockRabiSpectroscopyDipoleTrapMixin,
)
from repository.lib.experiment_templates.mixins.flir_blue_mot_measurement import (
    FLIRBlueMOTMeasurementMixin,
)
from repository.lib.experiment_templates.mixins.pumped_lattice import (
    OpticalPumpingWithFieldSettingDipoleTrapMixin,
)
from repository.lib.experiment_templates.mixins.XODT_molasses import (
    XODTSingleMolassesPlusFieldRampMixin,
)

logger = logging.getLogger(__name__)


class ClockSpecFromXXODTFrag(
    ClockRabiSpectroscopyDipoleTrapMixin,
    DoubleTrapImagingNormalised,
    FLIRBlueMOTMeasurementMixin,
    XODTSingleMolassesPlusFieldRampMixin,
    DipoleTrapWithExperiment,
    OpticalPumpingWithFieldSettingDipoleTrapMixin,
):
    """
    Clock spectroscopy from dropped XXODT

    Load into an XXODT, then use the up clock beam for spectroscopy, altering the
    (single-pass) AOM.

    Image the ground state atoms, repump and image the excited state, then image
    once more for background.
    """

    def host_setup(self):
        super().host_setup()

        # TODO: Make this not a horrible hack
        logger.warning("Setting EMCCD gain to 30. BEWARE!!!")
        self.andor_camera_control.cam.set_EMCCD_gain(30)

    @kernel
    def before_start_hook(self):
        self.before_start_hook_clockspec()
        self.before_start_hook_xodt_molasses()

    def host_cleanup(self):
        logger.warning("EM gain turned off again")
        self.andor_camera_control.cam.set_EMCCD_gain(0)
        return super().host_cleanup()


ClockSpecFromXXODT = make_fragment_scan_exp(ClockSpecFromXXODTFrag)
