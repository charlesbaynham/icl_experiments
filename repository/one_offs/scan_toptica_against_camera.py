from artiq.coredevice.core import Core
from artiq.experiment import now_mu
from ndscan.experiment import *
from ndscan.experiment.parameters import FloatParamHandle
from toptica_wrapper.driver import TopticaDLCPro
from wand.server import ControlInterface as WANDControlInterface

from repository.lib.fragments.blue_3d_mot import Blue3DMOTFrag
from repository.lib.fragments.dual_camera_measurer import DualCameraMeasurement
from repository.lib.fragments.set_eom_sidebands import SetEOMSidebandsFrag

MAX_VOLTAGE_STEP = 5.0


class LoadingSr87Frag(ExpFragment):
    def build_fragment(self) -> None:
        self.setattr_device("core")
        self.core: Core

        self.setattr_fragment("blue_mot", Blue3DMOTFrag)
        self.blue_mot: Blue3DMOTFrag

        self.setattr_fragment(
            "dual_cameras", DualCameraMeasurement, hardware_trigger=True
        )
        self.dual_cameras: DualCameraMeasurement

        self.setattr_fragment("eom_sidebands", SetEOMSidebandsFrag)
        self.eom_sidebands: SetEOMSidebandsFrag

        self.setattr_device("wand_server")
        self.wand_server: WANDControlInterface

        self.setattr_device("toptica_679")
        self.toptica_679: TopticaDLCPro

        self.setattr_device("toptica_707")
        self.toptica_707: TopticaDLCPro

        self.setattr_param(
            "toptica_707_voltage",
            FloatParam,
            default=50,
            description="Toptica 707 ECDL voltage",
            unit="V",
        )
        self.toptica_707_voltage: FloatParamHandle

        self.setattr_param(
            "toptica_679_voltage",
            FloatParam,
            default=50,
            description="Toptica 679 ECDL voltage",
            unit="V",
        )
        self.toptica_679_voltage: FloatParamHandle

        self.setattr_argument("clearout", BooleanValue(default=True))

        self.setattr_result("frequency_461")
        self.setattr_result("frequency_707")
        self.setattr_result("frequency_679")

        self.frequency_461: FloatChannel
        self.frequency_707: FloatChannel
        self.frequency_679: FloatChannel

    def host_setup(self):
        # Open a connection
        self.toptica_679.get_dlcpro().open()
        self.toptica_707.get_dlcpro().open()

        self.toptica_679_laser = self.toptica_679.get_laser()
        self.toptica_707_laser = self.toptica_707.get_laser()
        return super().host_setup()

    @kernel
    def run_once(self) -> None:
        new_679_voltage = self.toptica_679_voltage.get()
        new_707_voltage = self.toptica_707_voltage.get()

        self.set_topticas(new_679_voltage, new_707_voltage)

        self.core.break_realtime()
        self.eom_sidebands.set_sidebands()

        self.blue_mot.load_mot(clearout=self.clearout)
        self.dual_cameras.trigger()

        self.core.wait_until_mu(now_mu())
        self.dual_cameras.save_data()

        # Wavemeter measurements
        self.get_frequencies()

    @rpc
    def get_frequencies(self):
        _, freq_461, _ = self.wand_server.get_freq("461")
        _, freq_707, _ = self.wand_server.get_freq("707")
        _, freq_679, _ = self.wand_server.get_freq("679")

        self.frequency_461.push(freq_461)
        self.frequency_707.push(freq_707)
        self.frequency_679.push(freq_679)

    @rpc
    def set_topticas(self, new_679_voltage: TFloat, new_707_voltage: TFloat):
        current_679_voltage = self.toptica_679_laser.dl.pc.voltage_set.get()
        if abs(new_679_voltage - current_679_voltage) > MAX_VOLTAGE_STEP:
            raise ValueError(
                f"{new_679_voltage}V is too far from the current value of {current_679_voltage}V for the 679"
            )

        current_707_voltage = self.toptica_707_laser.dl.pc.voltage_set.get()
        if abs(new_707_voltage - current_707_voltage) > MAX_VOLTAGE_STEP:
            raise ValueError(
                f"{new_707_voltage}V is too far from the current value of {current_707_voltage}V for the 707"
            )

        self.toptica_679_laser.dl.pc.voltage_set.set(new_679_voltage)
        self.toptica_707_laser.dl.pc.voltage_set.set(new_707_voltage)


LoadingSr87 = make_fragment_scan_exp(LoadingSr87Frag)
