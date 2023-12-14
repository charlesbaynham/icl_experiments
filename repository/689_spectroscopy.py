import logging

from artiq.experiment import delay
from artiq.experiment import delay_mu
from artiq.experiment import kernel
from artiq.experiment import parallel
from artiq.experiment import sequential
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
                    "y": self.andor_camera_control.andor_roi_sum,
                },
                constants={
                    "t_dead": 0,
                },
            ),
            OnlineFit(
                "decaying_sinusoid",
                data={
                    "x": self.spectroscopy_pulse_time,
                    "y": self.andor_camera_control.andor_roi_mean,
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

        # The camera shutter needs ~120ms to open, so start this at the
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
            self.andor_camera_control.trigger(control_shutter=False)
            self.camera_interface.trigger()
            with sequential:
                self.fluorescence_pulse.do_imaging_pulse()
                self.andor_camera_control.set_shutter(False)

        self._save_data()


MeasureRedMOTSpectroscopy = make_fragment_scan_exp(MeasureRedMOTSpectroscopyFrag)
