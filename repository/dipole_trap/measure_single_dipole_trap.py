import logging

from artiq.language import delay
from artiq.language import kernel
from ndscan.experiment.entry_point import make_fragment_scan_exp
from ndscan.experiment.parameters import FloatParam
from ndscan.experiment.parameters import FloatParamHandle
from pyaion.fragments.suservo import LibSetSUServoStatic

from repository.lib import constants
from repository.lib.experiment_templates.mixins.andor_imaging.absorption_imaging import (
    AbsorptionDipoleTrapMixin,
)
from repository.lib.experiment_templates.mixins.andor_imaging.bg_corrected_andor_image import (
    BGCorrectedAndorImageSingleXODT,
)
from repository.lib.experiment_templates.mixins.evaporation_mixin import (
    EvaporationSingleRampMixin,
)
from repository.lib.experiment_templates.mixins.flir_measurement import (
    FLIRMeasurementMixin,
)
from repository.lib.experiment_templates.mixins.trap_frequencies_mixin import SwitchHODT
from repository.lib.experiment_templates.mixins.XODT_loading import LoadSingleXODTMixin

logger = logging.getLogger(__name__)


class MeasureSingleXODTBGCorrectedFrag(
    FLIRMeasurementMixin,
    BGCorrectedAndorImageSingleXODT,
    LoadSingleXODTMixin,
):
    """
    Make Single XODT, image twice for BG subtraction
    """

    @kernel
    def DMA_initialization_hook(self):
        self.DMA_initialization_hook_default()
        self.DMA_initialization_hook_loading_xodt_mot()

    @kernel
    def do_experiment_after_dipole_trap_hook(self):
        pass


class SingleXODTSloshedFrag(
    FLIRMeasurementMixin,
    BGCorrectedAndorImageSingleXODT,
    LoadSingleXODTMixin,
):
    """
    Slosh a single XODT

    Make Single XODT, hold it for some time, turn off the vertical trap, let it
    slosh then image
    """

    def build_fragment(self):
        self.setattr_param(
            "slosh_time",
            FloatParam,
            "Time to slosh the XODT for",
            default=0,
            unit="ms",
            min=0,
        )
        self.slosh_time: FloatParamHandle

        self.setattr_fragment(
            "down_813_suservo",
            LibSetSUServoStatic,
            constants.SUSERVOED_BEAMS["down_813"].suservo_device,
        )
        self.down_813_suservo: LibSetSUServoStatic

        super().build_fragment()

    @kernel
    def DMA_initialization_hook(self):
        self.DMA_initialization_hook_default()
        self.DMA_initialization_hook_loading_xodt_mot()

    @kernel
    def post_dipole_trap_hook(self):
        """
        Override post_dipole_trap_hook so that the beams are not turned off
        """

    @kernel
    def do_experiment_after_dipole_trap_hook(self):
        """
        Turn off the vertical trap then wait then image
        """

        self.down_813_suservo.set_channel_state(rf_switch_state=False, enable_iir=False)
        delay(self.slosh_time.get())


class SingleXODTVerticalSloshedFrag(
    FLIRMeasurementMixin,
    BGCorrectedAndorImageSingleXODT,
    LoadSingleXODTMixin,
    EvaporationSingleRampMixin,
    SwitchHODT,
):
    """
    Vertically slosh a single XODT

    Make Single XODT, decrease HODT depth to displace the atoms under gravity,
    switch up the HODT depth and let it slosh, then drop and image
    """


class MeasureSingleXODTAbsFrag(
    AbsorptionDipoleTrapMixin,
    LoadSingleXODTMixin,
):
    """
    Measure a single XODT with absorption imaging
    """

    @kernel
    def DMA_initialization_hook(self):
        self.DMA_initialization_hook_default()
        self.DMA_initialization_hook_loading_xodt_mot()

    @kernel
    def do_experiment_after_dipole_trap_hook(self):
        pass


MeasureSingleXODTBGCorrectedFrag = make_fragment_scan_exp(
    MeasureSingleXODTBGCorrectedFrag
)
MeasureSingleXODTAbsFrag = make_fragment_scan_exp(MeasureSingleXODTAbsFrag)
SingleXODTSloshed = make_fragment_scan_exp(SingleXODTSloshedFrag)
SingleXODTVerticalSloshed = make_fragment_scan_exp(SingleXODTVerticalSloshedFrag)
