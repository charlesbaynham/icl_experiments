import logging

from artiq.language import delay
from artiq.language import kernel
from ndscan.experiment.parameters import FloatParam
from ndscan.experiment.parameters import FloatParamHandle
from single_image_normalised_fast_kinetics_base import (
    SingleImageNormalisedFastKineticsBase,
)
from single_image_normalised_fast_kinetics_base import (
    SingleImageNormalisedFastKineticsDoubleTrapClockPulseBase,
)
from single_image_normalised_fast_kinetics_base import (
    SingleImageNormalisedFastKineticsDoubleTrapInterferometryBase,
)
from single_image_normalised_fast_kinetics_base import (
    SingleImageNormalisedFastKineticsDoubleTrapRepumpedBase,
)
from single_image_normalised_fast_kinetics_base import (
    SingleImageNormalisedFastKineticsDoubleTrapSpectroscopyBase,
)
from single_image_normalised_fast_kinetics_base import (
    SingleImageNormalisedFastKineticsSingleTrapBase,
)

from repository.lib import constants
from repository.lib.experiment_templates.mixins.clock_spectroscopy import (
    ClockSpectroscopyBase,
)

logger = logging.getLogger(__name__)
ANDOR_FK_G_BG_CORR_DATASET = "g_bg_corrected"
ANDOR_FK_E_BG_CORR_DATASET = "e_bg_corrected"


class SingleImageNormalisedDipoleTrapFastKineticsMixin(
    SingleImageNormalisedFastKineticsSingleTrapBase
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

    def time_dropped_before_first_pulse(self):
        """
        Need to fill this out
        """

        return


class SingleImageNormalisedFastKineticsRepumpedMixin(
    SingleImageNormalisedFastKineticsSingleTrapBase
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


#### DOUBLE TRAP CODE #####


class SingleImageNormalisedFastKineticsRepumpedInterferometryMixin(
    SingleImageNormalisedFastKineticsDoubleTrapInterferometryBase,
    SingleImageNormalisedFastKineticsDoubleTrapRepumpedBase,
):
    """
    Repumped and inteferometry timing
    """


class SingleImageNormalisedFastKineticsClockPulseInterferometryMixin(
    SingleImageNormalisedFastKineticsDoubleTrapInterferometryBase,
    SingleImageNormalisedFastKineticsDoubleTrapClockPulseBase,
):
    """
    Clock pulse and inteferometry timing
    """


class SingleImageNormalisedFastKineticsRepumpedSpectroscopyMixin(
    SingleImageNormalisedFastKineticsDoubleTrapSpectroscopyBase,
    SingleImageNormalisedFastKineticsDoubleTrapRepumpedBase,
):
    """
    707 Repumper and spectroscopy timing
    """
