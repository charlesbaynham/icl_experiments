import logging

from artiq.experiment import kernel
from ndscan.experiment.entry_point import make_fragment_scan_exp

from repository.lib.experiment_templates.mixins.andor_imaging.absorption_imaging import (
    AbsorptionDipoleTrapMixin,
)
from repository.lib.experiment_templates.mixins.andor_imaging.bg_corrected_andor_image import (
    BGCorrectedAndorImage,
)
from repository.lib.experiment_templates.mixins.andor_imaging.single_andor_image import (
    SingleAndorImage,
)
from repository.lib.experiment_templates.mixins.constant_lattice import (
    ConstantBeamsMixin,
)
from repository.lib.experiment_templates.mixins.flir_measurement import (
    FLIRMeasurementMixin,
)
from repository.lib.experiment_templates.dipole_trap_experiment import (
    DipoleTrapWithExperiment,
)

from artiq.experiment import delay
from artiq.experiment import delay_mu
from numpy import int64

logger = logging.getLogger(__name__)


class _MeasureSingleXODTFrag(DipoleTrapWithExperiment):
    """
    Loads atoms into a single XODT after the narrowband red MOT, without any molasses and spinpol.

    Kernel hooks used (multiple mixins cannot use the same hooks):

    * :meth:`~before_start_hook`

    We also override this hook to do nothing since this Mixin is now taking charge
    of field setting:

    * :meth:`~set_postnarrowband_fields_hook`
    """
    def build_fragment(self):
        super().build_fragment()

        # Remove unused parameters
        self.override_param("delay_after_experiment", 0)
        self.override_param("spectroscopy_field_gradient", 0)

    @kernel
    def before_start_hook(self):
        self.before_start_hook_single_xodt()

    @kernel
    def before_start_hook_single_xodt(self):
        """
        Before the blue MOT, turn on the crossed dipole trap beams and
        set setpoints to same as the start of the xodt molasses ramp.

        TODO: Move this to a device_setup / use a default beam setter to define setpoints
        """

        self.core.break_realtime()
        self.dipole_beam_controller.XODT_setter.turn_on_all()
        delay_mu(int64(self.core.ref_multiplier))
        self.core.break_realtime()
        self.dipole_beam_controller.set_dipole_suservo_setpoints(
            setpoint_down_813=self.molasses_xodt_1.default_suservo_setpoint_multiples_start[
                5
            ],
            setpoint_dipole_trap_1064_delivery=self.molasses_xodt_1.default_suservo_setpoint_multiples_start[
                4
            ],
        )

class MeasureSingleXODTBGCorrectedFrag(
    FLIRMeasurementMixin,
    BGCorrectedAndorImage,
    _MeasureSingleXODTFrag,
):
    """
    Make Single XODT, image twice for BG subtraction
    """

    @kernel
    def do_experiment_after_dipole_trap_hook(self):
        pass    

class MeasureSingleXODTAbsFrag(
    AbsorptionDipoleTrapMixin,
    _MeasureSingleXODTFrag,
):
    """
    Measure a single XODT, no molasses, with absorption imaging
    """

    @kernel
    def do_experiment_after_dipole_trap_hook(self):
        pass

MeasureSingleXODTBGCorrectedFrag = make_fragment_scan_exp(MeasureSingleXODTBGCorrectedFrag)
MeasureSingleXODTAbsFrag = make_fragment_scan_exp(MeasureSingleXODTAbsFrag)
