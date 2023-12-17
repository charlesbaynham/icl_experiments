import logging

from artiq.experiment import delay
from artiq.experiment import delay_mu
from artiq.experiment import kernel
from artiq.experiment import now_mu
from artiq.experiment import parallel
from artiq.experiment import sequential
from ndscan.experiment import FloatChannel
from ndscan.experiment import OnlineFit
from ndscan.experiment.entry_point import make_fragment_scan_exp
from ndscan.experiment.parameters import FloatParam
from ndscan.experiment.parameters import FloatParamHandle
from numpy import int64
from pyaion.fragments.suservo import LibSetSUServoStatic

from repository.measure_red_mot import RedMOTBase

logger = logging.getLogger(__name__)


class MeasureRedMOTSpectroscopyFrag(RedMOTBase):
    def build_fragment(self):
        # Set this frag up first, so that later fragments' device_setup override it
        self.setattr_fragment(
            "red_axial_minus",
            LibSetSUServoStatic,
            "suservo_aom_singlepass_689_red_mot_sigmaminus",
        )
        self.red_axial_minus: LibSetSUServoStatic

        super().build_fragment()

        self.setattr_param(
            "spectroscopy_pulse_time",
            FloatParam,
            "Length of spectroscopy pulse",
            default=50e-6,
            unit="us",
        )
        self.spectroscopy_pulse_time: FloatParamHandle

        self.setattr_param(
            "spectroscopy_pulse_aom_detuning",
            FloatParam,
            "Frequency detuning of AOM during spectroscopy pulse",
            default=0,
            unit="kHz",
        )
        self.spectroscopy_pulse_aom_detuning: FloatParamHandle

        self.setattr_param(
            "spectroscopy_pulse_aom_amplitude",
            FloatParam,
            "Amplitude of delivery AOM during spectroscopy pulse. SUServoing is disabled",
            default=1.0,
            min=0.0,
            max=1.0,
        )
        self.spectroscopy_pulse_aom_amplitude: FloatParamHandle

        self.setattr_param(
            "delay_after_spectroscopy",
            FloatParam,
            "Delay after spectroscopy before imaging",
            default=6e-6,
            unit="us",
        )
        self.delay_after_spectroscopy: FloatParamHandle

    def get_default_analyses(self):
        return [
            OnlineFit(
                "decaying_sinusoid",
                data={
                    "x": self.spectroscopy_pulse_time,
                    "y": self.andor_mean,
                },
                constants={
                    "t_dead": 0,
                },
            ),
            OnlineFit(
                "decaying_sinusoid",
                data={
                    "x": self.spectroscopy_pulse_time,
                    "y": self.andor_sum,
                },
                constants={
                    "t_dead": 0,
                },
            ),
        ]

    @kernel
    def run_once(self):
        self.core.break_realtime()
        self._from_start_to_end_of_broadband_mot()

        # The FLIR cameras are not useful for the final imaging, so use them to
        # image the blue MOT instead
        delay(-self.red_broadband_time.get() - 10e-3)
        self.camera_interface.trigger()
        delay(+self.red_broadband_time.get() + 10e-3)

        # The Andor camera shutter needs ~120ms to open, so start this at the
        # beginning of the red stages. If the total red mot sequence takes less
        # time than this then we'll have problems
        delay(-self.red_broadband_time.get())
        self.andor_camera_control.set_shutter(True)
        delay(+self.red_broadband_time.get())

        self.red_mot.transition_broadband_to_narrowband()

        self.red_mot.chamber_2_field_setter.set_mot_gradient(0.0)
        delay_mu(int64(self.core.ref_multiplier))
        self.red_mot.red_beam_controller.turn_off_mot_beams(ignore_shutters=True)
        delay_mu(int64(self.core.ref_multiplier))
        self.red_mot.red_beam_controller.set_mot_detuning(
            self.spectroscopy_pulse_aom_detuning.get()
        )
        delay_mu(int64(self.core.ref_multiplier))
        self.blue_3d_mot.turn_off_repumpers()
        delay_mu(int64(self.core.ref_multiplier))
        self.red_axial_minus.suservo_channel.set_y(
            profile=self.red_axial_minus.suservo_profile,
            y=self.spectroscopy_pulse_aom_amplitude.get(),
        )

        delay(self.expansion_time.get())

        self.red_axial_minus.set_channel_state(rf_switch_state=True, enable_iir=False)
        delay(self.spectroscopy_pulse_time.get())
        self.red_mot.red_beam_controller.turn_off_mot_beams()

        delay(self.delay_after_spectroscopy.get())

        with parallel:
            self.andor_camera_control.trigger(
                exposure=self.fluorescence_pulse.fluorescence_pulse_duration.get(),
                control_shutter=False,
            )
            with sequential:
                self.fluorescence_pulse.do_imaging_pulse()
                self.andor_camera_control.set_shutter(False)

        self._save_data()


class BlowAwayMOTFrag(MeasureRedMOTSpectroscopyFrag):
    def build_fragment(self):
        super().build_fragment()

        self.setattr_param(
            "delay_between_fluoresence_pulses",
            FloatParam,
            "Delay after first fluorescence pulse before second",
            default=1e-3,
            unit="ms",
        )
        self.delay_between_fluoresence_pulses: FloatParamHandle

        self.setattr_result("andor_sum_2", FloatChannel)
        self.setattr_result("andor_mean_2", FloatChannel)
        self.andor_sum_2: FloatChannel
        self.andor_mean_2: FloatChannel

        self.setattr_result("excitation_fraction", FloatChannel)
        self.excitation_fraction: FloatChannel

    @kernel
    def run_once(self):
        self.core.break_realtime()
        self._from_start_to_end_of_broadband_mot()

        # The FLIR cameras are not useful for the final imaging, so use them to
        # image the blue MOT instead
        delay(-self.red_broadband_time.get() - 10e-3)
        self.camera_interface.trigger()
        delay(+self.red_broadband_time.get() + 10e-3)

        # The Andor camera shutter needs ~120ms to open, so start this at the
        # beginning of the red stages. If the total red mot sequence takes less
        # time than this then we'll have problems
        delay(-self.red_broadband_time.get())
        self.andor_camera_control.set_shutter(True)
        delay(+self.red_broadband_time.get())

        self.red_mot.transition_broadband_to_narrowband()

        self.red_mot.chamber_2_field_setter.set_mot_gradient(0.0)
        delay_mu(int64(self.core.ref_multiplier))
        self.red_mot.red_beam_controller.turn_off_mot_beams(ignore_shutters=True)
        delay_mu(int64(self.core.ref_multiplier))
        self.red_mot.red_beam_controller.set_mot_detuning(
            self.spectroscopy_pulse_aom_detuning.get()
        )
        delay_mu(int64(self.core.ref_multiplier))
        self.blue_3d_mot.turn_off_repumpers()
        delay_mu(int64(self.core.ref_multiplier))
        self.red_axial_minus.suservo_channel.set_y(
            profile=self.red_axial_minus.suservo_profile,
            y=self.spectroscopy_pulse_aom_amplitude.get(),
        )

        delay(self.expansion_time.get())

        self.red_axial_minus.set_channel_state(rf_switch_state=True, enable_iir=False)
        delay(self.spectroscopy_pulse_time.get())
        self.red_axial_minus.set_channel_state(rf_switch_state=False, enable_iir=False)

        delay(self.delay_after_spectroscopy.get())

        andor_exposure = 2 * self.fluorescence_pulse.fluorescence_pulse_duration.get()

        delay(-0.5 * andor_exposure)
        self.andor_camera_control.trigger(
            exposure=andor_exposure,
            control_shutter=False,
        )
        delay(0.5 * andor_exposure)
        self.fluorescence_pulse.do_imaging_pulse(ignore_final_shutters=True)

        delay(self.delay_between_fluoresence_pulses.get())

        delay(-0.5 * andor_exposure)
        self.andor_camera_control.trigger(
            exposure=andor_exposure,
            control_shutter=False,
        )
        delay(0.5 * andor_exposure)
        self.fluorescence_pulse.do_imaging_pulse(ignore_final_shutters=True)

        self.andor_camera_control.set_shutter(False)

        # Save blue MOT pics
        self.core.wait_until_mu(now_mu())
        self.camera_interface.save_data()

        # Save 2x Andor pics
        sums = [0, 0]
        means = [0.0, 0.0]
        self.andor_camera_control.readout_images(
            sums,
            means,
            self.core.get_rtio_counter_mu() + self.core.seconds_to_mu(1.0),
            num_images=2,
        )

        self.andor_sum.push(sums[0])
        self.andor_sum_2.push(sums[1])
        self.andor_mean.push(means[0])
        self.andor_mean_2.push(means[1])

        self.excitation_fraction.push(means[1] / (means[0] + means[1]))

        # TODO: Move this closing of red mot shutters somewhere more sensible
        self.core.break_realtime()
        self.red_mot.red_beam_controller.turn_off_mot_beams()


MeasureRedMOTSpectroscopy = make_fragment_scan_exp(MeasureRedMOTSpectroscopyFrag)
BlowAwayMOT = make_fragment_scan_exp(BlowAwayMOTFrag)
