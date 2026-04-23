import logging

from artiq.language import delay
from artiq.language import kernel
from ndscan.experiment.parameters import FloatParam
from ndscan.experiment.parameters import FloatParamHandle
from single_image_normalised_fast_kinetics_base import (
    SingleImageNormalisedFastKineticsBase,
)
from single_image_normalised_fast_kinetics_base import (
    SingleImageNormalisedFastKineticsDoubleTrapBase,
)
from single_image_normalised_fast_kinetics_base import calculate_grabber_rois

from repository.lib import constants
from repository.lib.experiment_templates.mixins.clock_spectroscopy import (
    ClockSpectroscopyBase,
)

logger = logging.getLogger(__name__)
ANDOR_FK_G_BG_CORR_DATASET = "g_bg_corrected"
ANDOR_FK_E_BG_CORR_DATASET = "e_bg_corrected"


class SingleImageNormalisedDipoleTrapFastKineticsMixin(
    SingleImageNormalisedFastKineticsBase
):
    """
    Implements normalised readout for a :py:class:`~RedMOTWithExperiment`
    experiment

    This is a mixin - see the documentation for :mod:`~.red_mot_experiment` for
    details.

    Kernel hooks used (multiple mixins cannot use the same hooks):

    * :meth:`~do_imaging_hook_andor`
    * :meth:`~process_andor_data_hook`
    * :meth:`~update_andor_monitor_hook`
    """

    fast_kinetics_height_default = constants.ANDOR_FAST_KINETICS_HEIGHT_DIPOLE_TRAP
    fast_kinetics_offset_default = constants.ANDOR_FAST_KINETICS_OFFSET_DIPOLE_TRAP

    def get_grabber_roi_defaults(self):
        return calculate_grabber_rois(
            fast_kinetics_height=self.fast_kinetics_height_default,
            fast_kinetics_offset=self.fast_kinetics_offset_default,
            num_images=self.num_images_per_series,
            x0=constants.ANDOR_ROI_DIPOLE_TRAP_FORWARD_SINGLE_IMAGE_X0,
            y0=constants.ANDOR_ROI_DIPOLE_TRAP_FORWARD_SINGLE_IMAGE_Y0,
            x1=constants.ANDOR_ROI_DIPOLE_TRAP_FORWARD_SINGLE_IMAGE_X1,
            y1=constants.ANDOR_ROI_DIPOLE_TRAP_FORWARD_SINGLE_IMAGE_Y1,
            bg_width=constants.ANDOR_SINGLE_FAST_KINETICS_BACKGROUND_ROI_WIDTH,
            excited_shift=constants.ROI_SHIFT_EXCITED_STATE,
        )


class SingleImageNormalisedFastKineticsRepumpedMixin(
    SingleImageNormalisedFastKineticsBase
):
    """
    Adds repumping after the first fluorescence pulse to a
    :class:`~.SingleImageNormalisedFastKineticsBase` experiment.

    This is a mixin for :class:`~.SingleImageNormalisedFastKineticsBase`.

    Kernel hooks used (multiple mixins cannot use the same hooks):

    * :meth:`~do_first_pulse`
    * :meth:`~do_imaging_hook_andor`
    """

    def build_fragment(self):
        super().build_fragment()

        self.setattr_param(
            "delay_repumps_after_first_pulse",
            FloatParam,
            "Delay after first fluorescence pulse before repumps turn on",
            default=0.01e-3,
            unit="ms",
        )
        self.delay_repumps_after_first_pulse: FloatParamHandle

    @kernel
    def do_first_pulse(self):
        self.do_pulse()
        delay(self.delay_repumps_after_first_pulse.get())
        self.blue_3d_mot.turn_on_repumpers()


class SingleImageNormalisedFastKineticsClockPulseMixin(
    SingleImageNormalisedFastKineticsBase, ClockSpectroscopyBase
):
    """
    Adds a clock pi pulse after the first fluorescence pulse to a
    :class:`~.SingleImageNormalisedFastKineticsBase` experiment, in order to selectively
    bring the excited state in the ground state before imaging.

    This is a mixin for :class:`~.NormalisedFastKineticsBase`.

    Kernel hooks used (multiple mixins cannot use the same hooks):

    * :meth:`~do_first_pulse`
    * :meth:`~do_imaging_hook_andor`
    """

    def build_fragment(self):
        super().build_fragment()

        self.setattr_param(
            "delay_clock_after_first_pulse",
            FloatParam,
            "Delay after first fluorescence pulse before the pi pulse",
            default=0.01e-3,
            unit="ms",
        )
        self.delay_clock_after_first_pulse: FloatParamHandle

        self.setattr_param(
            "imaging_clock_pulse_detuning",
            FloatParam,
            "Detuning for the imaging clock pulse",
            default=0.0,
            unit="kHz",
        )
        self.imaging_clock_pulse_detuning: FloatParamHandle

    @kernel
    def do_first_pulse(self):
        self.do_pulse()
        delay(self.delay_clock_after_first_pulse.get())
        self.clock_down_dds.set(
            frequency=self.clock_switch_frequency_handle.get()
            + self.imaging_clock_pulse_detuning.get()
            + constants.LMT_DOWN_BEAM_SHIFT,
            amplitude=self.clock_switch_amplitude_handle.get(),
        )

        delay(1e-6)

        # PI PULSE

        self.clock_down_dds.sw.on()
        delay(constants.CLOCK_DOWN_PI_TIME)
        self.clock_down_dds.sw.off()


class SingleImageNormalisedFastKineticsDoubleTrapRepumpedMixin(
    SingleImageNormalisedFastKineticsDoubleTrapBase
):
    """
    Adds repumping after the first fluorescence pulse to a
    :class:`~.SingleImageNormalisedFastKineticsDoubleTrapBase` experiment.

    This is a mixin for :class:`~.SingleImageNormalisedFastKineticsDoubleTrapBase`.

    Kernel hooks used (multiple mixins cannot use the same hooks):

    * :meth:`~do_first_pulse`
    * :meth:`~do_imaging_hook_andor`
    """

    def build_fragment(self):
        super().build_fragment()

        self.setattr_param(
            "delay_repumps_after_first_pulse",
            FloatParam,
            "Delay after first fluorescence pulse before repumps turn on",
            default=0.01e-3,
            unit="ms",
        )
        self.delay_repumps_after_first_pulse: FloatParamHandle

    @kernel
    def do_first_pulse(self):
        self.do_pulse()
        delay(self.delay_repumps_after_first_pulse.get())
        self.blue_3d_mot.turn_on_repumpers()
