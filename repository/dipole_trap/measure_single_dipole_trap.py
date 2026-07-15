import logging

from artiq.language import delay
from artiq.language import kernel
from ndscan.experiment.entry_point import make_fragment_scan_exp
from ndscan.experiment.parameters import BoolParam
from ndscan.experiment.parameters import BoolParamHandle
from ndscan.experiment.parameters import FloatParam
from ndscan.experiment.parameters import FloatParamHandle
from pyaion.fragments.suservo import LibSetSUServoStatic

from repository.lib import constants
from repository.lib.experiment_templates.mixins.andor_imaging.absorption_imaging import (
    AbsorptionDipoleTrapMixin,
)
from repository.lib.experiment_templates.mixins.andor_imaging.bg_corrected_andor_image import (
    BGCorrectedAndorImageSingleXODTMixin,
)
from repository.lib.experiment_templates.mixins.andor_imaging.em_gain import EMGainMixin
from repository.lib.experiment_templates.mixins.evaporation_mixin import (
    EvaporationSingleRampMixin,
)
from repository.lib.experiment_templates.mixins.evaporation_mixin import (
    EvaporationThreeRampsMixin,
)
from repository.lib.experiment_templates.mixins.evaporation_mixin import (
    FieldOnlyRampInEvapMixin,
)
from repository.lib.experiment_templates.mixins.flir_measurement import (
    FLIRMeasurementMixin,
)
from repository.lib.experiment_templates.mixins.optical_pumping import (
    OpticalPumpingWithFieldSettingDipoleTrapMixin,
)
from repository.lib.experiment_templates.mixins.painted_quadratic import (
    AdiabaticCoolingWithPaintedQuadraticMixin,
)
from repository.lib.experiment_templates.mixins.trap_frequencies_mixin import (
    HorizontalKickMixin,
)
from repository.lib.experiment_templates.mixins.trap_frequencies_mixin import (
    SwitchHODTMixin,
)
from repository.lib.experiment_templates.mixins.XODT_loading import LoadSingleXODTMixin
from repository.lib.experiment_templates.mixins.XODT_loading import (
    LoadSingleXODTWithPainterMixin,
)
from repository.lib.experiment_templates.mixins.XODT_molasses import (
    XODTSingleMolassesMixin,
)
from repository.lib.experiment_templates.mixins.XODT_molasses import (
    XODTSingleMolassesPlusDipoleRampMixin,
)

logger = logging.getLogger(__name__)


class MeasureSingleXODTBGCorrectedFrag(
    FLIRMeasurementMixin,
    BGCorrectedAndorImageSingleXODTMixin,
    LoadSingleXODTMixin,
):
    """
    Make Single XODT and image twice for BG subtraction
    """

    @kernel
    def DMA_initialization_hook(self):
        self.DMA_initialization_hook_redmot_default()
        self.DMA_initialization_hook_loading_xodt_mot()
        self.DMA_initialization_hook_dipole_trap_default()

    @kernel
    def do_experiment_after_dipole_trap_hook(self):
        pass


class MeasureSingleXODTWithMolassesBGCorrectedFrag(
    FLIRMeasurementMixin,
    BGCorrectedAndorImageSingleXODTMixin,
    LoadSingleXODTMixin,
    XODTSingleMolassesMixin,
):
    """
    Transparency-beam bring-up check: a single XODT with a molasses stage.

    Adds the transparency-protected molasses cooling stage on top of
    :class:`MeasureSingleXODTBGCorrectedFrag`. With a healthy transparency beam
    the molasses recaptures atoms into the trap, so the BG-corrected atom number
    is *higher* than the plain (no-molasses) XODT. A blocked or dark transparency
    beam instead lets the molasses light blast the trapped atoms, so the atom
    number does not rise (and typically falls). Comparing this against
    :class:`MeasureSingleXODTBGCorrectedFrag` is therefore a remote health check
    for the transparency beam.

    ``protect_with_transparency`` False skips the transparency turn-on, forcing
    the dead-beam case: it must destroy the enhancement, which is what makes this
    a check that can actually fail.
    """

    def build_fragment(self):
        self.setattr_param(
            "protect_with_transparency",
            BoolParam,
            "Turn the transparency beam on during the molasses stage",
            default=True,
        )
        self.protect_with_transparency: BoolParamHandle

        kernel_invariants = getattr(self, "kernel_invariants", set())
        self.kernel_invariants = kernel_invariants | {
            "protect_with_transparency_invariant",
        }

        super().build_fragment()

    def host_setup(self):
        # Bools cannot be scanned, so bake it in as a kernel invariant
        self.protect_with_transparency_invariant = self.protect_with_transparency.get()
        return super().host_setup()

    @kernel
    def do_experiment_after_dipole_trap_hook(self):
        pass

    @kernel
    def dipole_trap_molasses_hook_first_xodt_molasses(self):
        # Mirrors XODTSingleMolassesMixin, gating the transparency turn-on so the
        # dead-beam case can be reproduced on demand.
        red_suservos = (
            self.red_mot.red_beam_controller.all_beam_default_setter.suservo_setters_and_info
        )
        for i in range(len(red_suservos)):
            red_suservos[i].setter.set_setpoint(0.0)
        self.red_mot.red_beam_controller.all_mot_beams_setter.turn_beams_on(
            ignore_shutters=True
        )
        if self.protect_with_transparency_invariant:
            self.transparency_setter.turn_on_all()
        self.blue_3d_mot.repump_beam_setter.turn_beams_on()
        self.blue_3d_mot.mirny_eom_sidebands.set_689_stir_sideband_detuning(
            detuning=self.stir_beam_detuning_molasses_1.get()
        )

        self.molasses_xodt_1.do_phase()

        self.transparency_suservo.set_channel_state(
            rf_switch_state=False, enable_iir=False
        )
        self.blue_3d_mot.repump_beam_setter.turn_beams_off(ignore_shutters=True)
        self.red_mot.red_beam_controller.all_mot_beams_setter.turn_beams_off(
            ignore_shutters=True
        )


class SingleXODTSloshedFrag(
    FLIRMeasurementMixin,
    BGCorrectedAndorImageSingleXODTMixin,
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
        self.DMA_initialization_hook_redmot_default()
        self.DMA_initialization_hook_loading_xodt_mot()
        self.DMA_initialization_hook_dipole_trap_default()

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
    BGCorrectedAndorImageSingleXODTMixin,
    LoadSingleXODTMixin,
    XODTSingleMolassesMixin,
    EvaporationSingleRampMixin,
    SwitchHODTMixin,
):
    """
    Vertically slosh a single XODT

    Make Single XODT, decrease HODT depth to displace the atoms under gravity,
    switch up the HODT depth and let it slosh, then drop and image
    """


class SingleXODTHorizontalYSloshedFrag(
    FLIRMeasurementMixin,
    BGCorrectedAndorImageSingleXODTMixin,
    EMGainMixin,
    LoadSingleXODTMixin,
    XODTSingleMolassesMixin,
    EvaporationThreeRampsMixin,
    HorizontalKickMixin,
):
    """
    Horizontally slosh a single XODT

    Load an XODT, use evaporation ramps to keep the coldest atoms and to ramp back up
    to desired trap depth, then use a spinpol beam to displace the atoms horizontally
    """

    # TODO: Rebind the evaporation params to a single ramp down followed by a ramp up

    @kernel
    def do_experiment_after_dipole_trap_hook(self):
        pass


class MeasureSingleXODTAbsFrag(
    AbsorptionDipoleTrapMixin,
    LoadSingleXODTMixin,
):
    """
    Measure a single XODT with absorption imaging
    """

    @kernel
    def DMA_initialization_hook(self):
        self.DMA_initialization_hook_redmot_default()
        self.DMA_initialization_hook_loading_xodt_mot()
        self.DMA_initialization_hook_dipole_trap_default()

    @kernel
    def do_experiment_after_dipole_trap_hook(self):
        pass


class MeasureCooledXODTFrag(
    FLIRMeasurementMixin,
    BGCorrectedAndorImageSingleXODTMixin,
    XODTSingleMolassesPlusDipoleRampMixin,
    OpticalPumpingWithFieldSettingDipoleTrapMixin,
    FieldOnlyRampInEvapMixin,
    AdiabaticCoolingWithPaintedQuadraticMixin,
    LoadSingleXODTWithPainterMixin,
):
    """
    Measure a Single XODT with adiabatic cooling and delta kick
    """

    @kernel
    def DMA_initialization_hook(self):
        self.DMA_initialization_hook_redmot_default()
        self.DMA_initialization_hook_adiabatic_cooling()
        self.DMA_initialization_hook_painter_on()
        self.DMA_initialization_hook_evap_with_field_ramp()
        self.DMA_initialization_hook_loading_xodt_mot()
        self.DMA_initialization_hook_xodt_molasses()
        self.DMA_initialization_hook_dipole_trap_default()

    @kernel
    def post_sequence_cleanup_hook(self):
        self.post_narrowband_hook_default()
        self.post_sequence_cleanup_hook_andor()
        self.post_sequence_cleanup_hook_loading()

    @kernel
    def do_experiment_after_dipole_trap_hook(self):
        pass


MeasureSingleXODTBGCorrected = make_fragment_scan_exp(MeasureSingleXODTBGCorrectedFrag)
MeasureSingleXODTWithMolassesBGCorrected = make_fragment_scan_exp(
    MeasureSingleXODTWithMolassesBGCorrectedFrag
)
MeasureSingleXODTAbs = make_fragment_scan_exp(MeasureSingleXODTAbsFrag)
MeasureCooledXODT = make_fragment_scan_exp(MeasureCooledXODTFrag)
SingleXODTSloshed = make_fragment_scan_exp(SingleXODTSloshedFrag)
SingleXODTVerticalSloshed = make_fragment_scan_exp(SingleXODTVerticalSloshedFrag)
SingleXODTHorizontalYSloshed = make_fragment_scan_exp(SingleXODTHorizontalYSloshedFrag)
