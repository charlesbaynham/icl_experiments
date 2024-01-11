import logging

import numpy as np
from artiq.coredevice.ad9910 import AD9910
from artiq.coredevice.suservo import Channel as SUServoChannel
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


class TripleImageMOTFrag(RedMOTBase):
    """
    Run a sequence that makes a red MOT, allows setting of expansion and coils,
    does something to it (e.g. a spectroscopy or interferometry sequence) then
    images it with three shots in fast kinetics.

    This ExpFragment cannot be used as is - you should subclass it and implement
    at least the `do_spectroscopy_hook` method and possible the other
    `..._hook` methods.
    """

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
        # Set this frag up first, so that later fragments' device_setup override it
        self.pre_build_fragment_hook()

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

        self.setattr_param(
            "extra_repump_time",
            FloatParam,
            "Time to keep repumps on during expansion",
            default=0,
            unit="us",
        )
        self.extra_repump_time: FloatParamHandle

        self.setattr_param(
            "delay_between_fluoresence_pulses",
            FloatParam,
            "Delay after first fluorescence pulse before second",
            default=1e-3,
            unit="ms",
        )
        self.delay_between_fluoresence_pulses: FloatParamHandle

        self.setattr_param(
            "delay_before_background_pulse",
            FloatParam,
            "Delay after final fluorescence pulse before background measurement",
            default=10e-3,
            unit="ms",
        )
        self.delay_before_background_pulse: FloatParamHandle

        self.setattr_param(
            "spectroscopy_field_gradient",
            FloatParam,
            "MOT coil current during spectroscopy",
            default=0.0,
            unit="A",
        )
        self.spectroscopy_field_gradient: FloatParamHandle

        for c in "xyz":
            self.setattr_param(
                f"{c}_coil_boost",
                FloatParam,
                default=0.0,
                description=f"Boost to {c} coil current",
                unit="A",
            )
        self.x_coil_boost: FloatParamHandle
        self.y_coil_boost: FloatParamHandle
        self.z_coil_boost: FloatParamHandle

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

        t_light_off_mu = now_mu()
        self.red_mot.red_beam_controller.turn_off_mot_beams(ignore_shutters=True)

        delay_mu(int64(self.core.ref_multiplier))
        self.red_mot.red_beam_controller.set_mot_detuning(
            self.spectroscopy_pulse_aom_detuning.get()
        )

        delay(self.extra_repump_time.get())
        delay_mu(int64(self.core.ref_multiplier))
        self.blue_3d_mot.turn_off_repumpers()
        delay(-self.extra_repump_time.get())

        self.pre_expansion_hook()

        # Ensure that the expansion time isn't affected by durations of SPI
        # transfers etc.
        at_mu(t_light_off_mu)

        self.red_mot.chamber_2_field_setter.set_all_fields(
            self.spectroscopy_field_gradient.get(),
            self.blue_3d_mot.chamber_2_bias_x.get() + self.x_coil_boost.get(),
            self.blue_3d_mot.chamber_2_bias_y.get() + self.y_coil_boost.get(),
            self.blue_3d_mot.chamber_2_bias_z.get() + self.z_coil_boost.get(),
        )

        delay(self.expansion_time.get())

        # Do the spectroscopy / interfereometry / whatever sequence. This method
        # must be defined by child classes
        self.do_spectroscopy_hook()

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
        delay(self.delay_before_background_pulse.get())
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

    # %% Hooks
    #
    # The remaining methods in this class are designed to be overridden by
    # children of this class, to control its behaviour. `do_spectroscopy_hook`
    # is compulsory, the others are optional. See `run_once` to understand where
    # these hooks are executed.

    def pre_build_fragment_hook(self):
        """
        Hook run at the beginning of `build_fragment`

        TODO: Remove this, users can just override build_fragment and user
        `super()` as god intended.
        """
        pass

    @kernel
    def before_start_hook(self):
        """
        Hook for core actions before the start of the atomics sequence.

        Feel free to use break_realtime - it will be called again before the MOT
        is loaded.
        """
        pass

    @kernel
    def pre_expansion_hook(self):
        """
        Hook for core actions after the narrowband red mot is completed, before
        cloud expansion begins
        """
        pass

    @kernel
    def do_spectroscopy_hook(self):
        """
        Hook for the implementation of a spectroscopy / interfereometry /
        whatever pulse, executed after the programmed expansion time is
        completed.
        """
        raise NotImplementedError


class SpectroscopyWithKinetics_MOTBeam(TripleImageMOTFrag):
    """
    689nm spectroscopy MOTBEAM

    689nm spectroscopy with fast kinetics imaging using the red MOT beam
    """

    def pre_build_fragment_hook(self):
        self.setattr_fragment(
            "red_axial_minus",
            LibSetSUServoStatic,
            "suservo_aom_singlepass_689_red_mot_sigmaminus",
        )
        self.red_axial_minus: LibSetSUServoStatic

    @kernel
    def pre_expansion_hook(self):
        self.red_axial_minus.suservo_channel.set_y(
            profile=self.red_axial_minus.suservo_profile,
            y=self.spectroscopy_pulse_aom_amplitude.get(),
        )

    @kernel
    def do_spectroscopy_hook(self):
        self.red_axial_minus.set_channel_state(rf_switch_state=True, enable_iir=False)
        delay(self.spectroscopy_pulse_time.get())
        self.red_axial_minus.set_channel_state(rf_switch_state=False, enable_iir=False)


class SpectroscopyWithKinetics_UpBeam(TripleImageMOTFrag):
    """
    689nm spectroscopy UP

    689nm spectroscopy with fast kinetics imaging using the red up beam
    """

    def pre_build_fragment_hook(self):
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
    def do_spectroscopy_hook(self):
        self.up_beam_suservo.set_channel_state(rf_switch_state=True, enable_iir=False)
        delay(self.spectroscopy_pulse_time.get())
        self.up_beam_suservo.set_channel_state(rf_switch_state=False, enable_iir=False)


class UpBeamInterferometryFrag(SpectroscopyWithKinetics_UpBeam):
    """
    Up beam interferometry - IJD phase shift
    """

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
            "phase_step",
            FloatParam,
            "Phase step in interferometry sequence",
            default=0.0,
        )
        self.phase_step: FloatParamHandle

    def host_setup(self):
        super().host_setup()

        self.setattr_device("urukul9910_aom_doublepass_689_red_injection")
        self.urukul9910_aom_doublepass_689_red_injection: AD9910

    def get_default_analyses(self):
        super_analysis = super().get_default_analyses()

        return super_analysis + [
            OnlineFit(
                "sinusoid",
                data={
                    "x": self.phase_step,
                    "y": self.excitation_fraction,
                },
                constants={
                    "t_dead": -100.0,
                },
            )
        ]

    @kernel
    def do_spectroscopy_hook(self):
        t_pi_pulse = self.spectroscopy_pulse_time.get()

        # Allow negative phases up to -10
        phase_constant = 10.0

        # A bit fragile, but recalculate the injection AOM's frequency here
        freq = (
            constants.RED_INJECTION_AOM_FREQUENCY
            + self.red_mot.red_beam_controller.injection_aom_static_detuning.get()
            + self.spectroscopy_pulse_aom_detuning.get()
        )

        # Set initial phase
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
            phase=0.5 * self.phase_step.get() + phase_constant,
        )

        delay(self.delay_between_interferometry_pulses.get())

        # PI PULSE
        self.up_beam_suservo.set_channel_state(rf_switch_state=True, enable_iir=False)
        delay(t_pi_pulse)
        self.up_beam_suservo.set_channel_state(rf_switch_state=False, enable_iir=False)

        # Phase step again
        self.urukul9910_aom_doublepass_689_red_injection.set(
            frequency=freq,
            phase=2.0 * self.phase_step.get() + phase_constant,
        )

        delay(self.delay_between_interferometry_pulses.get())

        # PI/2 PULSE
        self.up_beam_suservo.set_channel_state(rf_switch_state=True, enable_iir=False)
        delay(t_pi_pulse / 2)
        self.up_beam_suservo.set_channel_state(rf_switch_state=False, enable_iir=False)


class UpBeamInterferometrySUServoPhaseFrag(UpBeamInterferometryFrag):
    """
    Up beam interferometry - delivery phase shift
    """

    def host_setup(self):
        super().host_setup()

        self.setattr_device("suservo_aom_singlepass_689_up")
        self.suservo_aom_singlepass_689_up: SUServoChannel

        # Kernel vars
        self.suservo_freq = constants.AOM_BEAMS["red_up"].frequency
        # Allow negative phases up to -10
        self.phase_constant = 10.0

    @kernel
    def before_start_hook(self):
        # Enable the Up beam with default settings, but turn off the AOM and open the shutter
        self.core.break_realtime()
        self.up_beam_default_setter.turn_on_all(light_enabled=True)

        # Set up SUServo profiles manually with config options for different phases
        self.suservo_aom_singlepass_689_up.set_dds(
            0, frequency=self.suservo_freq, offset=0.0, phase=self.phase_constant
        )
        self.suservo_aom_singlepass_689_up.set_dds(
            1,
            frequency=self.suservo_freq,
            offset=0.0,
            phase=self.phase_constant + 1.0 * self.phase_step.get(),
        )
        self.suservo_aom_singlepass_689_up.set_dds(
            2,
            frequency=self.suservo_freq,
            offset=0.0,
            phase=self.phase_constant + 4.0 * self.phase_step.get(),
        )

        for i in range(3):
            self.suservo_aom_singlepass_689_up.set_y(
                profile=i,
                y=self.spectroscopy_pulse_aom_amplitude.get(),
            )

        # Start on profile 0 with AOM off
        self.suservo_aom_singlepass_689_up.set(en_out=0, en_iir=0, profile=0)

    @kernel
    def do_spectroscopy_hook(self):
        t_pi_pulse = self.spectroscopy_pulse_time.get()

        # Ensure we're on profile 0
        self.suservo_aom_singlepass_689_up.set(en_out=0, en_iir=0, profile=0)

        delay(self.delay_between_interferometry_pulses.get())

        # PI/2 PULSE
        self.suservo_aom_singlepass_689_up.set(en_out=1, en_iir=0, profile=0)
        delay(t_pi_pulse / 2)
        # Phase step & turn off
        self.suservo_aom_singlepass_689_up.set(en_out=0, en_iir=0, profile=1)

        delay(self.delay_between_interferometry_pulses.get())

        # PI PULSE
        self.suservo_aom_singlepass_689_up.set(en_out=1, en_iir=0, profile=1)
        delay(t_pi_pulse)
        # Phase step and turn off
        self.suservo_aom_singlepass_689_up.set(en_out=0, en_iir=0, profile=2)

        delay(self.delay_between_interferometry_pulses.get())

        # PI/2 PULSE
        self.suservo_aom_singlepass_689_up.set(en_out=1, en_iir=0, profile=2)
        delay(t_pi_pulse / 2)
        self.suservo_aom_singlepass_689_up.set(en_out=0, en_iir=0, profile=0)


SpectroscopyWithKineticsExp = make_fragment_scan_exp(SpectroscopyWithKinetics_MOTBeam)
UpBeamBlowaway = make_fragment_scan_exp(SpectroscopyWithKinetics_UpBeam)
UpBeamInterferometry = make_fragment_scan_exp(UpBeamInterferometryFrag)
UpBeamInterferometrySUServoPhase = make_fragment_scan_exp(
    UpBeamInterferometrySUServoPhaseFrag
)
