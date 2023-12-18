import logging

from artiq.coredevice.ad9910 import AD9910
from artiq.experiment import at_mu
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
from pyaion.fragments.beam_setter import ControlBeamsWithoutCoolingAOM
from pyaion.fragments.suservo import LibSetSUServoStatic

from repository.lib import constants
from repository.lib.fragments.andor_camera import AndorCameraControl
from repository.lib.fragments.beam_setters import SetBeamsToDefaults
from repository.measure_red_mot import RedMOTBase

logger = logging.getLogger(__name__)


class MeasureRedMOTSpectroscopyFrag(RedMOTBase):
    def setup_spectroscopy_subfrag(self):
        self.setattr_fragment(
            "red_axial_minus",
            LibSetSUServoStatic,
            "suservo_aom_singlepass_689_red_mot_sigmaminus",
        )
        self.red_axial_minus: LibSetSUServoStatic

    def build_fragment(self):
        # Set this frag up first, so that later fragments' device_setup override it
        self.setup_spectroscopy_subfrag()

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
    def before_start_hook(self):
        pass

    @kernel
    def run_once(self):
        self.before_start_hook()

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
    def get_default_analyses(self):
        return [
            OnlineFit(
                "decaying_sinusoid",
                data={
                    "x": self.spectroscopy_pulse_time,
                    "y": self.excitation_fraction,
                },
                constants={
                    "t_dead": 0,
                },
            )
        ]

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

        self.setattr_param(
            "spectroscopy_field_gradient",
            FloatParam,
            "MOT coil current during spectroscopy",
            default=0.0,
            unit="A",
        )
        self.spectroscopy_field_gradient: FloatParamHandle

    def _setup_andor(self):
        """
        Setup the Andor camera

        Overrides the parent implementation so that we have 3x ROIs

        TODO: Set up Fast Kinetics mode here
        """

        # 3x ROIs
        self.setattr_fragment(
            "andor_camera_control",
            AndorCameraControl,
            roi_defaults=[
                [
                    constants.ANDOR_ROI_X0,
                    i * constants.ANDOR_FAST_KINETICS_HEIGHT,
                    constants.ANDOR_ROI_X1,
                    (i + 1) * constants.ANDOR_FAST_KINETICS_HEIGHT,
                ]
                for i in range(3)
            ],
        )
        self.andor_camera_control: AndorCameraControl

        self.setattr_result("andor_sum_gnd", FloatChannel)
        self.setattr_result("andor_sum_ex", FloatChannel)
        self.setattr_result("andor_sum_bg", FloatChannel)
        self.setattr_result("excitation_fraction", FloatChannel)
        self.andor_sum_gnd: FloatChannel
        self.andor_sum_ex: FloatChannel
        self.andor_sum_bg: FloatChannel
        self.excitation_fraction: FloatChannel

    @kernel
    def run_once(self):
        self.before_start_hook()

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

        self.red_mot.chamber_2_field_setter.set_mot_gradient(
            self.spectroscopy_field_gradient.get()
        )
        delay_mu(int64(self.core.ref_multiplier))
        t_light_off_mu = now_mu()
        self.red_mot.red_beam_controller.turn_off_mot_beams(ignore_shutters=True)
        delay_mu(int64(self.core.ref_multiplier))
        self.red_mot.red_beam_controller.set_mot_detuning(
            self.spectroscopy_pulse_aom_detuning.get()
        )
        delay_mu(int64(self.core.ref_multiplier))
        self.blue_3d_mot.turn_off_repumpers()
        delay_mu(int64(self.core.ref_multiplier))

        self.setup_spectroscopy_beam_before_expansion()

        # Ensure that the expansion time isn't affected by durations of SPI
        # transfers etc.
        at_mu(t_light_off_mu)
        delay(self.expansion_time.get())

        self.do_spectroscopy_pulse()

        delay(self.delay_after_spectroscopy.get())

        andor_exposure = 2 * self.fluorescence_pulse.fluorescence_pulse_duration.get()

        # Image gnd state atoms
        delay(-0.5 * andor_exposure)
        self.andor_camera_control.trigger(
            exposure=andor_exposure,
            control_shutter=False,
        )
        delay(0.5 * andor_exposure)
        self.fluorescence_pulse.do_imaging_pulse(ignore_final_shutters=True)

        delay(self.delay_between_fluoresence_pulses.get())

        # Image excited state atoms
        delay(-0.5 * andor_exposure)
        self.andor_camera_control.trigger(
            exposure=andor_exposure,
            control_shutter=False,
        )
        delay(0.5 * andor_exposure)
        self.fluorescence_pulse.do_imaging_pulse(ignore_final_shutters=True)

        # Take background measurement
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

        # Save Andor data
        sums = [0] * 3
        means = [0.0] * 3
        self.andor_camera_control.readout_ROIs(
            sums,
            means,
            self.core.get_rtio_counter_mu() + self.core.seconds_to_mu(1.0),
        )

        self.andor_sum_gnd.push(sums[0])
        self.andor_sum_ex.push(sums[1])
        self.andor_sum_bg.push(sums[2])

        self.excitation_fraction.push(
            (means[1] - means[2]) / (means[0] + means[1] - 2 * means[2])
        )

        # TODO: Move this closing of red mot shutters somewhere more sensible
        self.core.break_realtime()
        self.red_mot.red_beam_controller.turn_off_mot_beams()

    @kernel
    def setup_spectroscopy_beam_before_expansion(self):
        self.red_axial_minus.suservo_channel.set_y(
            profile=self.red_axial_minus.suservo_profile,
            y=self.spectroscopy_pulse_aom_amplitude.get(),
        )

    @kernel
    def do_spectroscopy_pulse(self):
        self.red_axial_minus.set_channel_state(rf_switch_state=True, enable_iir=False)
        delay(self.spectroscopy_pulse_time.get())
        self.red_axial_minus.set_channel_state(rf_switch_state=False, enable_iir=False)


class UpBeamBlowawayFrag(BlowAwayMOTFrag):
    def setup_spectroscopy_subfrag(self):
        class _UpBeamSetter(SetBeamsToDefaults):
            default_beam_infos = [constants.AOM_BEAMS["red_up"]]

        self.setattr_fragment("up_beam_default_setter", _UpBeamSetter)
        self.up_beam_default_setter: SetBeamsToDefaults

        self.setattr_fragment(
            "up_beam_suservo",
            LibSetSUServoStatic,
            constants.AOM_BEAMS["red_up"].suservo_device,
        )
        self.up_beam_suservo: LibSetSUServoStatic

    @kernel
    def before_start_hook(self):
        # Enable the Up beam with default settings, but turn off the AOM and open the shutter
        self.core.break_realtime()
        self.up_beam_default_setter.turn_on_all(light_enabled=True)
        self.up_beam_suservo.set_channel_state(rf_switch_state=False, enable_iir=False)
        self.up_beam_suservo.suservo_channel.set_y(
            profile=self.up_beam_suservo.suservo_profile,
            y=self.spectroscopy_pulse_aom_amplitude.get(),
        )

    @kernel
    def setup_spectroscopy_beam_before_expansion(self):
        pass

    @kernel
    def do_spectroscopy_pulse(self):
        self.up_beam_suservo.set_channel_state(rf_switch_state=True, enable_iir=False)
        delay(self.spectroscopy_pulse_time.get())
        self.up_beam_suservo.set_channel_state(rf_switch_state=False, enable_iir=False)


class UpBeamInterferometryFrag(UpBeamBlowawayFrag):
    def build_fragment(self):
        super().build_fragment()

        self.setattr_param(
            "delay_between_interferometry_pulses",
            FloatParam,
            "Delay between interferometry pulses",
            default=100e-9,
            unit="us",
        )
        self.delay_between_interferometry_pulses: FloatParamHandle

        self.setattr_param(
            "phase_step_for_pi_pulse",
            FloatParam,
            "Phase step for pi pulse",
            default=0.0,
        )
        self.phase_step_for_pi_pulse: FloatParamHandle

        self.setattr_device("urukul9910_aom_doublepass_689_red_injection")
        self.urukul9910_aom_doublepass_689_red_injection: AD9910

        # Kernel vars
        self.up_beam_aom_freq = constants.AOM_BEAMS["red_up"].frequency

    @kernel
    def do_spectroscopy_pulse(self):
        t_pi_pulse = self.spectroscopy_pulse_time.get()
        phase_constant = (
            0.0  # Stolen from BHam - no idea why we would want this but I'm debugging
        )

        freq = (
            constants.RED_INJECTION_AOM_FREQUENCY
            + self.red_mot.red_beam_controller.injection_aom_static_detuning.get()
            + self.spectroscopy_pulse_aom_detuning.get()
        )

        # Set frequency and offset manually so we can control the phase
        # self.up_beam_suservo.suservo_channel.set_dds(
        #     profile=self.up_beam_suservo.suservo_profile,
        #     frequency=self.up_beam_aom_freq,
        #     offset=0.0,  # unused
        #     phase=0.0,
        # )

        self.urukul9910_aom_doublepass_689_red_injection.set(
            frequency=freq, phase=phase_constant
        )

        delay(self.delay_between_interferometry_pulses.get())

        # PI/2 PULSE
        self.up_beam_suservo.set_channel_state(rf_switch_state=True, enable_iir=False)
        delay(t_pi_pulse / 2)
        self.up_beam_suservo.set_channel_state(rf_switch_state=False, enable_iir=False)

        # Phase step
        self.urukul9910_aom_doublepass_689_red_injection.set(
            frequency=freq,
            phase=0.5 * self.phase_step_for_pi_pulse.get() + phase_constant,
        )

        delay(self.delay_between_interferometry_pulses.get())

        # PI PULSE
        self.up_beam_suservo.set_channel_state(rf_switch_state=True, enable_iir=False)
        delay(t_pi_pulse)
        self.up_beam_suservo.set_channel_state(rf_switch_state=False, enable_iir=False)

        # Phase step
        self.urukul9910_aom_doublepass_689_red_injection.set(
            frequency=freq,
            phase=2.0 * self.phase_step_for_pi_pulse.get() + phase_constant,
        )

        delay(self.delay_between_interferometry_pulses.get())

        # PI/2 PULSE
        self.up_beam_suservo.set_channel_state(rf_switch_state=True, enable_iir=False)
        delay(t_pi_pulse / 2)
        self.up_beam_suservo.set_channel_state(rf_switch_state=False, enable_iir=False)


MeasureRedMOTSpectroscopy = make_fragment_scan_exp(MeasureRedMOTSpectroscopyFrag)
BlowAwayMOT = make_fragment_scan_exp(BlowAwayMOTFrag)
UpBeamBlowaway = make_fragment_scan_exp(UpBeamBlowawayFrag)
UpBeamInterferometry = make_fragment_scan_exp(UpBeamInterferometryFrag)
