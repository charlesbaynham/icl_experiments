import logging

from artiq.coredevice.core import Core
from artiq.experiment import delay
from artiq.experiment import kernel
from ndscan.experiment.entry_point import make_fragment_scan_exp
from ndscan.experiment.parameters import FloatParam
from ndscan.experiment.parameters import FloatParamHandle
from pyaion.fragments.default_beam_setter import SetBeamsToDefaults
from pyaion.fragments.default_beam_setter import make_set_beams_to_default
from pyaion.fragments.suservo import LibSetSUServoStatic

from repository.lib import constants
from repository.lib.experiment_templates.dipole_trap_experiment import (
    DipoleTrapWithExperiment,
)
from repository.lib.experiment_templates.mixins.andor_imaging.double_trap_imaging import (
    DoubleTrapImagingBGSubtracted,
)
from repository.lib.experiment_templates.mixins.andor_imaging.em_gain import EMGain
from repository.lib.experiment_templates.mixins.flir_measurement import (
    FLIRMeasurementMixin,
)
from repository.lib.experiment_templates.mixins.XODT_molasses import (
    XODTSingleMolassesMixin,
)
from repository.lib.fragments.checkpoint_fragment import RedMOTCheckpoints

logger = logging.getLogger(__name__)


class DownBeamAlignmentFrag(RedMOTCheckpoints):
    def build_fragment(self):
        self.setattr_device("core")
        self.core: Core

        # Automatic setup of the down beam
        self.setattr_fragment(
            "down_beam_setup",
            make_set_beams_to_default(
                suservo_beam_infos=[constants.SUSERVOED_BEAMS["down_689"]],
                use_automatic_setup=False,
            ),
        )
        self.down_beam_setup: SetBeamsToDefaults

        # Add control of the down beam
        self.setattr_fragment(
            "down_beam",
            LibSetSUServoStatic,
            constants.SUSERVOED_BEAMS["down_689"].suservo_device,
        )
        self.down_beam: LibSetSUServoStatic

        self.setattr_param(
            "down_beam_pulse_time",
            FloatParam,
            default=10e-3,
            description="Duration of down beam pulse",
            unit="ms",
        )
        self.down_beam_pulse_time: FloatParamHandle

    @kernel
    def device_setup(self):
        self.device_setup_subfragments()

        self.core.break_realtime()
        delay(1e-3)

        # Configure the down beam but leave it off
        self.core.break_realtime()
        self.down_beam_setup.turn_on_all(light_enabled=False)

    @kernel
    def do_experiment_after_dipole_trap_hook(self):
        # Blast the atoms with the down beam
        if self.down_beam_pulse_time.get() > 0.0:
            self.down_beam.set_channel_state(rf_switch_state=True, enable_iir=True)
            delay(self.down_beam_pulse_time.get())
            self.down_beam.set_channel_state(rf_switch_state=False, enable_iir=False)


class DownBeamAlignmentExp(
    DoubleTrapImagingBGSubtracted,
    FLIRMeasurementMixin,
    XODTSingleMolassesMixin,
    EMGain,
    DipoleTrapWithExperiment,
):
    """
    Make a double XODT and blast it with the down beam before imaging
    """

    def build_fragment(self):
        super().build_fragment()

        self.setattr_fragment("down_beam_alignment", DownBeamAlignmentFrag)
        self.down_beam_alignment: DownBeamAlignmentFrag

        self.setattr_param_rebind("down_beam_pulse_time", self.down_beam_alignment)

    @kernel
    def post_dipole_trap_hook(self):
        # Override the default post-dipole trap hook to keep the dipole trap on
        pass

    @kernel
    def do_experiment_after_dipole_trap_hook(self):
        self.down_beam_alignment.do_experiment_after_dipole_trap_hook()


DownBeamAlignment = make_fragment_scan_exp(DownBeamAlignmentExp)
