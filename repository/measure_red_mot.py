import logging

from artiq.coredevice.core import Core
from artiq.experiment import at_mu
from artiq.experiment import delay
from artiq.experiment import delay_mu
from artiq.experiment import kernel
from artiq.experiment import now_mu
from artiq.experiment import parallel
from artiq.experiment import sequential
from ndscan.experiment import ExpFragment
from ndscan.experiment.entry_point import make_fragment_scan_exp
from ndscan.experiment.parameters import FloatParam
from ndscan.experiment.parameters import FloatParamHandle
from numpy import int64
from pyaion.fragments.suservo import LibSetSUServoStatic

from repository.lib import constants
from repository.lib.fragments.andor_camera import AndorCameraControl
from repository.lib.fragments.blue_3d_mot import Blue3DMOTFrag
from repository.lib.fragments.dual_camera_measurer import DualCameraMeasurement
from repository.lib.fragments.fluorescence_pulse import ToggleableFluorescencePulse
from repository.lib.fragments.red_mot import NarrowbandRedMOTFrag

logger = logging.getLogger(__name__)


class _RedMOTBase(ExpFragment):
    def build_fragment(self) -> None:
        self.setattr_device("core")
        self.core: Core

        # %% Fragments

        self.setattr_fragment("blue_3d_mot", Blue3DMOTFrag)
        self.blue_3d_mot: Blue3DMOTFrag

        self.setattr_fragment("red_mot", NarrowbandRedMOTFrag)
        self.red_mot: NarrowbandRedMOTFrag

        self.setattr_fragment(
            "camera_interface", DualCameraMeasurement, hardware_trigger=True
        )
        self.camera_interface: DualCameraMeasurement

        self.setattr_fragment("andor_camera_control", AndorCameraControl)
        self.andor_camera_control: AndorCameraControl

        self.setattr_fragment("fluorescence_pulse", ToggleableFluorescencePulse)
        self.fluorescence_pulse: ToggleableFluorescencePulse

        # %% Params

        # Expansion time - can be negative
        self.setattr_param(
            "expansion_time",
            FloatParam,
            "Time to expand MOT for before imaging",
            default=0.0,
            unit="us",
        )
        self.expansion_time: FloatParamHandle

        # %% Rebound params

        self.setattr_param_rebind(
            "exposure_horiz",
            self.camera_interface,
            "exposure_horiz",
            default=constants.DEFAULT_CAMERA_EXPOSURE_TIME,
            description="Horizontal camera exposure time",
            unit="us",
        )
        self.setattr_param_rebind(
            "exposure_vert",
            self.camera_interface,
            "exposure_vert",
            default=constants.DEFAULT_CAMERA_EXPOSURE_TIME,
            description="Vertical camera exposure time",
            unit="us",
        )
        self.exposure_horiz: FloatParamHandle
        self.exposure_vert: FloatParamHandle

        self.setattr_param_rebind(
            "injection_aom_static_detuning",
            self.red_mot,
        )
        self.setattr_param_rebind(
            "red_broadband_time",
            self.red_mot,
        )
        self.red_broadband_time: FloatParamHandle

    @kernel
    def _from_start_to_end_of_broadband_mot(self):
        self.blue_3d_mot.load_mot(clearout=True)
        self.blue_3d_mot.turn_off_3d_and_2d_beams()
        self.red_mot.start_red_broadband()
        delay(self.red_broadband_time.get())

    @kernel
    def _expand_and_image(self):
        self.red_mot.red_beam_controller.turn_off_mot_beams()
        delay(self.expansion_time.get())

        with parallel:
            self.andor_camera_control.trigger(control_shutter=True)
            self.fluorescence_pulse.do_imaging_pulse()
            self.camera_interface.trigger()

        # Turn the fields back to defaults so eddy currents are gone by the next shot
        delay(1e-3)
        self.blue_3d_mot.enable_mot_fields()

    @kernel
    def _save_data(self):
        "Consume all slack and save the photos"
        self.core.wait_until_mu(now_mu())
        self.camera_interface.save_data()
        self.andor_camera_control.save_data(
            self.core.get_rtio_counter_mu() + self.core.seconds_to_mu(1.0)
        )


class MeasureBBRedMOTFrag(_RedMOTBase):
    @kernel
    def run_once(self):
        self.core.break_realtime()
        self._from_start_to_end_of_broadband_mot()
        self._expand_and_image()
        self._save_data()


class MeasureNarrowbandMOTFrag(_RedMOTBase):
    @kernel
    def run_once(self):
        narrowband_duration = self.red_mot.get_total_narrowband_duration()

        self.core.break_realtime()
        self._from_start_to_end_of_broadband_mot()

        with parallel:
            with sequential:
                delay(narrowband_duration)
                self._expand_and_image()

            self.red_mot.transition_broadband_to_narrowband()

        self._save_data()


class MeasureRedMOTSpectroscopyFrag(_RedMOTBase):
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


MeasureBBRedMOT = make_fragment_scan_exp(MeasureBBRedMOTFrag)
MeasureNarrowbandRedMOT = make_fragment_scan_exp(MeasureNarrowbandMOTFrag)
MeasureRedMOTSpectroscopy = make_fragment_scan_exp(MeasureRedMOTSpectroscopyFrag)
