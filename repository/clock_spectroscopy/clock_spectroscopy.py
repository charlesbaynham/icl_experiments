import abc
import logging

from artiq.experiment import at_mu
from artiq.experiment import delay
from artiq.experiment import delay_mu
from artiq.experiment import kernel
from artiq.experiment import now_mu
from ndscan.experiment import FloatChannel
from ndscan.experiment import OnlineFit
from ndscan.experiment.entry_point import make_fragment_scan_exp
from ndscan.experiment.parameters import FloatParam
from ndscan.experiment.parameters import FloatParamHandle
from numpy import int64
from pyaion.fragments.suservo import LibSetSUServoStatic
from pyaion.models import SUServoedBeam

from repository.lib import constants
from repository.lib.fragments.beams.beam_setters import SetBeamsToDefaults
from repository.lib.fragments.cameras.andor_camera import AndorCameraControl
from repository.lib.fragments.cameras.triple_imaging_kinetics import (
    RedMOTWithExperiment,
)
from repository.lib.fragments.cameras.triple_imaging_kinetics import SpectroscopyMixin
from repository.red_mot.measure_red_mot import RedMOTBase

logger = logging.getLogger(__name__)

CLOCK_BEAM_INFO: SUServoedBeam = constants.AOM_BEAMS["clock_up"]


class BasicClockSpectroscopyFrag(SpectroscopyMixin, RedMOTWithExperiment):
    """
    Basic clock spectroscopy

    Use the up clock beam for spectroscopy, altering the (single-pass) AOM

    Image the ground state atoms, repump and image the excited state, then image
    once more for background
    """

    def build_fragment(self):
        super().build_fragment()

        self.setattr_param(
            "delay_after_first_pulse",
            FloatParam,
            "Delay after first fluorescence pulse before repumps turn on",
            default=1e-3,
            unit="ms",
        )
        self.delay_after_first_pulse: FloatParamHandle

        self.setattr_param(
            "delay_after_repumps_on",
            FloatParam,
            "Delay after repumps before second fluorescence pulse",
            default=1e-3,
            unit="ms",
        )
        self.delay_after_repumps_on: FloatParamHandle

        self.setattr_param(
            "delay_before_background_pulse",
            FloatParam,
            "Delay after final fluorescence pulse before background measurement",
            default=10e-3,
            unit="ms",
        )
        self.delay_before_background_pulse: FloatParamHandle

        self.setattr_result("andor_sum_0", FloatChannel)
        self.setattr_result("andor_sum_1", FloatChannel)
        self.setattr_result("andor_sum_2", FloatChannel)
        self.setattr_result("excitation_fraction", FloatChannel)
        self.andor_sum_0: FloatChannel
        self.andor_sum_1: FloatChannel
        self.andor_sum_2: FloatChannel
        self.excitation_fraction: FloatChannel

    def pre_build_fragment_hook(self):
        self.setattr_fragment(
            "clock_up",
            LibSetSUServoStatic,
            "suservo_aom_698_up_switch",
        )
        self.clock_up: LibSetSUServoStatic

    @kernel
    def before_start_hook(self):
        self.core.break_realtime()
        self.clock_up.set_suservo(
            freq=CLOCK_BEAM_INFO.frequency + self.spectroscopy_pulse_aom_detuning.get(),
            amplitude=self.spectroscopy_pulse_aom_amplitude.get(),
            attenuation=CLOCK_BEAM_INFO.attenuation,
            rf_switch_state=False,
            enable_iir=False,
        )

    @kernel
    def do_spectroscopy_hook(self):
        self.clock_up.set_channel_state(rf_switch_state=True, enable_iir=False)
        delay(self.spectroscopy_pulse_time.get())
        self.clock_up.set_channel_state(rf_switch_state=False, enable_iir=False)

    @kernel
    def do_imaging_hook(self):
        andor_exposure = 2 * self.fluorescence_pulse.fluorescence_pulse_duration.get()

        self.do_first_pulse(andor_exposure)
        delay(self.delay_after_first_pulse.get())
        self.blue_3d_mot.turn_on_repumpers()
        delay(self.delay_after_repumps_on.get())
        self.do_second_pulse(andor_exposure)
        delay(self.delay_before_background_pulse.get())
        self.do_third_pulse(andor_exposure)

    @kernel
    def save_data_hook(self):
        """
        Hook to save data from the Andor camera

        To make it easier, I'm not using fast kinetics but am just reading 3x normal images with the normal ROIs

        Runs in realtime after imaging is completed
        """
        # Save Andor data
        sums = [0] * 3
        means = [0.0] * 3
        for i in range(3):
            self.andor_camera_control.readout_ROIs(
                sums[i : i + 1],
                means[i : i + 1],
                self.core.get_rtio_counter_mu() + self.core.seconds_to_mu(1.0),
            )

        self.andor_sum_0.push(sums[0])
        self.andor_sum_1.push(sums[1])
        self.andor_sum_2.push(sums[2])

        print(sums)
        print(means)

        self.excitation_fraction.push(
            (means[1] - means[2]) / (means[0] + means[1] - 2 * means[2])
        )


BasicClockSpectroscopy = make_fragment_scan_exp(BasicClockSpectroscopyFrag)
