from artiq.coredevice.core import Core
from artiq.experiment import kernel
from artiq.experiment import now_mu
from ndscan.experiment import ExpFragment
from ndscan.experiment import delay
from ndscan.experiment.entry_point import make_fragment_scan_exp
from ndscan.experiment.parameters import FloatParam
from ndscan.experiment.parameters import FloatParamHandle
from pyaion.fragments.default_beam_setter import SetBeamsToDefaults
from pyaion.fragments.default_beam_setter import make_set_beams_to_default

from repository.lib import constants
from repository.lib.fragments.blue_3d_mot import Blue3DMOTFrag
from repository.lib.fragments.cameras.dual_camera_measurer import DualCameraMeasurement

PlugBeamSetter = make_set_beams_to_default(
    suservo_beam_infos=[
        constants.SUSERVOED_BEAMS["blue_plug_beam"],
    ],
    urukul_beam_infos=[],
    name="PlugBeamSetter",
    use_automatic_setup=True,
)


class ScanPlugBeamParamsFrag(ExpFragment):
    def build_fragment(self) -> None:
        self.setattr_device("core")
        self.core: Core

        # self.get_device("suservo_aom_doublepass_461_plug")

        # self.blue_aom = self.setattr_fragment(
        #     "blue_aom",
        #     LibSetSUServoStatic,
        #     constants.SUSERVOED_BEAMS["blue_plug_beam"].suservo_device,
        # )
        # self.blue_aom: LibSetSUServoStatic

        self.setattr_fragment("blue_mot", Blue3DMOTFrag)
        self.blue_mot: Blue3DMOTFrag

        self.setattr_fragment(
            "dual_cameras", DualCameraMeasurement, hardware_trigger=True
        )
        self.dual_cameras: DualCameraMeasurement

        self.setattr_fragment("plug_beam_default_setter", PlugBeamSetter)
        self.plug_beam_default_setter: SetBeamsToDefaults

        self.setattr_param_rebind("mot_loading_time", self.blue_mot, "loading_time")
        self.mot_loading_time: FloatParamHandle

        self.setattr_param(
            "delay_between_points",
            FloatParam,
            "Delay between measurements",
            default=20e-3,
            min=0,
            unit="s",
        )
        self.delay_between_points: FloatParamHandle

        # self.setattr_param(
        #     "plug_aom_attenuation",
        #     FloatParam,
        #     description="Attenuation on Urukul's variable attenuator",
        #     default=30,
        #     unit="dB",
        #     min=0,
        #     max=31.5,
        # )
        # self.plug_aom_attenuation: FloatParamHandle

        # self.setattr_param_rebind(
        #     "plug_beam_setpoint",
        #     self.plug_beam_default_setter,
        #     "setpoint_blue_plug_beam",
        #     description="Setpoint",
        # )
        # self.plug_beam_setpoint: FloatParamHandle

        # self.setattr_param_rebind(
        #     "plug_beam_frequency",
        #     self.plug_beam_default_setter,
        #     "frequency_blue_plug_beam",
        #     description="Frequency",
        # )
        # self.plug_beam_frequency: FloatParamHandle

        # self.setattr_param(
        #     "plug_aom_frequency",
        #     FloatParam,
        #     description="Frequency of plug beam AOM",
        #     default=165e6,
        #     unit="MHz",
        #     min=0,
        #     #    max=185e6,
        # )
        # self.plug_aom_frequency: FloatParamHandle

        # self.attenuation = constants.SUSERVOED_BEAMS["blue_plug_beam"].attenuation
        # self.initial_amplitude = constants.SUSERVOED_BEAMS[
        #     "blue_plug_beam"
        # ].initial_amplitude

    @kernel
    def run_once(self) -> None:
        # Turn on the plug beam and set its amplitude, setpoint and frequency
        self.plug_beam_default_setter.turn_on_all()

        # # Override its frequency. We must also set its setpoint again
        # self.blue_aom.set_suservo(
        #     freq=self.plug_aom_frequency.get(),
        #     amplitude=self.initial_amplitude,
        #     attenuation=self.attenuation,
        #     rf_switch_state=True,
        #     setpoint_v=self.plug_beam_setpoint.get(),
        # )

        self.blue_mot.load_mot()  # This turns on MOT coils, "clears out" for 100ms, then turns on MOT beams, and waits for loading time

        delay(500e-3)

        self.dual_cameras.trigger()

        self.core.wait_until_mu(now_mu())

        self.dual_cameras.save_data()

        self.core.break_realtime()

        self.blue_mot.turn_off_all_beams()

        delay(self.delay_between_points.get())


ScanPlugBeamParams = make_fragment_scan_exp(ScanPlugBeamParamsFrag)
