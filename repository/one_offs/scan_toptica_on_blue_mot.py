from artiq.coredevice.core import Core
from artiq.language import now_mu
from ndscan.experiment import BooleanValue
from ndscan.experiment import ExpFragment
from ndscan.experiment import FloatChannel
from ndscan.experiment import FloatParam
from ndscan.experiment import TFloat
from ndscan.experiment import kernel
from ndscan.experiment import make_fragment_scan_exp
from ndscan.experiment import rpc
from ndscan.experiment.parameters import FloatParamHandle
from toptica_wrapper.driver import TopticaDLCPro
from wand.server import ControlInterface as WANDControlInterface

from repository.lib.fragments.blue_3d_mot import Blue3DMOTFrag
from repository.lib.fragments.cameras.dual_camera_measurer import DualCameraMeasurement
from repository.lib.fragments.set_eom_sidebands import SetAllEOMSidebandsFrag

MAX_VOLTAGE_STEP = 5.0


class ScanTopticaMOTFrag(ExpFragment):
    def build_fragment(self) -> None:
        self.setattr_device("core")
        self.core: Core

        self.setattr_fragment("blue_mot", Blue3DMOTFrag)
        self.blue_mot: Blue3DMOTFrag

        self.setattr_fragment(
            "dual_cameras", DualCameraMeasurement, hardware_trigger=True
        )
        self.dual_cameras: DualCameraMeasurement

        self.setattr_fragment("eom_sidebands", SetAllEOMSidebandsFrag)
        self.eom_sidebands: SetAllEOMSidebandsFrag

        self.setattr_device("wand_server")
        self.wand_server: WANDControlInterface

        self.setattr_device("toptica_461")
        self.toptica_461: TopticaDLCPro

        self.setattr_device("toptica_679")
        self.toptica_679: TopticaDLCPro

        self.setattr_device("toptica_707")
        self.toptica_707: TopticaDLCPro

        self.setattr_param(
            "toptica_461_voltage",
            FloatParam,
            default=-1,
            description="Toptica 461 ECDL voltage (-1 = unchanged)",
            unit="V",
        )
        self.toptica_461_voltage: FloatParamHandle

        self.setattr_param(
            "toptica_707_voltage",
            FloatParam,
            default=-1,
            description="Toptica 707 ECDL voltage (-1 = unchanged)",
            unit="V",
        )
        self.toptica_707_voltage: FloatParamHandle

        self.setattr_param(
            "toptica_679_voltage",
            FloatParam,
            default=-1,
            description="Toptica 679 ECDL voltage (-1 = unchanged)",
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
        self.toptica_461.get_dlcpro().open()
        self.toptica_679.get_dlcpro().open()
        self.toptica_707.get_dlcpro().open()

        self.toptica_461_laser = self.toptica_461.get_laser()
        self.toptica_679_laser = self.toptica_679.get_laser()
        self.toptica_707_laser = self.toptica_707.get_laser()

        return super().host_setup()

    @kernel
    def run_once(self) -> None:
        new_461_voltage = self.toptica_461_voltage.get()
        new_679_voltage = self.toptica_679_voltage.get()
        new_707_voltage = self.toptica_707_voltage.get()

        self.set_topticas(
            new_461_voltage=new_461_voltage,
            new_679_voltage=new_679_voltage,
            new_707_voltage=new_707_voltage,
        )

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
    def set_topticas(
        self, new_461_voltage: TFloat, new_679_voltage: TFloat, new_707_voltage: TFloat
    ):
        lasers = [
            self.toptica_461_laser,
            self.toptica_679_laser,
            self.toptica_707_laser,
        ]

        new_voltages = [new_461_voltage, new_679_voltage, new_707_voltage]

        for laser, new_voltage in zip(lasers, new_voltages):
            if new_voltage < 0:
                continue

            current_voltage = laser.dl.pc.voltage_set.get()
            if abs(new_voltage - current_voltage) > MAX_VOLTAGE_STEP:
                raise ValueError(
                    f"{new_voltage}V is too far from the current value of {current_voltage}V for {laser}"
                )

            laser.dl.pc.voltage_set.set(new_voltage)


ScanTopticaMOT = make_fragment_scan_exp(ScanTopticaMOTFrag)
