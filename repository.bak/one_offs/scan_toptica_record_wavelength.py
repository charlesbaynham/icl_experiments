from artiq.experiment import EnumerationValue
from ndscan.experiment import ExpFragment
from ndscan.experiment import make_fragment_scan_exp
from ndscan.experiment.parameters import FloatParam
from ndscan.experiment.parameters import FloatParamHandle
from ndscan.experiment.result_channels import FloatChannel
from toptica_wrapper import TopticaDLCPro
from wand.server import ControlInterface as WANDControlInterface

from repository.lib import constants

TOPTICA_TO_WAND_NAMES = {
    "toptica_461": "461",
    "toptica_679": "679",
    "toptica_707": "707",
    "toptica_689": "689",
    "toptica_698": "698",
}


class ScanTopticaWithWavemeterFrag(ExpFragment):
    """
    Scan a Toptica laser and measure it with WAND

    Note: does not use the core.
    """

    laser_name = None

    def build_fragment(self) -> None:
        self.setattr_device("wand_server")
        self.wand_server: WANDControlInterface

        toptica_lasers = list(TOPTICA_TO_WAND_NAMES.keys())

        if self.laser_name is None:
            # Allow the user to choose the laser by subclassing this Fragment if
            # they want. Otherwise make an argument
            self.setattr_argument(
                "laser_name",
                EnumerationValue(toptica_lasers, default=toptica_lasers[0]),
            )
            self.laser_name: str

        self.setattr_param(
            "toptica_voltage",
            FloatParam,
            default=-1,
            description="Toptica ECDL voltage (-1 = unchanged)",
            unit="V",
        )
        self.toptica_voltage: FloatParamHandle

        self.setattr_param(
            "toptica_current",
            FloatParam,
            default=-1,
            description="Toptica ECDL current (-1 = unchanged)",
            unit="mA",
        )
        self.toptica_current: FloatParamHandle

        self.setattr_result(
            "frequency",
            FloatChannel,
            display_hints={"priority": -1},
            description="Measured laser frequency",
            unit="MHz",
        )
        self.setattr_result(
            "detuning",
            FloatChannel,
            description="Measured laser detuning",
            unit="MHz",
        )

        self.frequency: FloatChannel
        self.detuning: FloatChannel

    def host_setup(self):
        # Get the laser controller and open a connection to it. This is done in
        # host_setup since the user can choose which laser they're using
        self.laser_controller: TopticaDLCPro = self.get_device(self.laser_name)

        # Open a connection
        self.laser_controller.get_dlcpro().open()
        self.laser = self.laser_controller.get_laser()

        # Get the laser's nominal setpoint
        self.nominal_setpoint = constants.WAND_SETPOINTS_87[
            TOPTICA_TO_WAND_NAMES[self.laser_name]
        ][0]

        # Make sure that the slew rate protection is on
        slew_rate_protection_enabled = (
            self.laser.dl.pc.output_filter.slew_rate_enabled.get()
        )
        if not slew_rate_protection_enabled:
            raise RuntimeError(
                f"Slew rate protection is not enabled for {self.laser_name}. "
                "Please enable it in the Toptica GUI and set a save value."
            )

        return super().host_setup()

    def run_once(self):
        self.set_toptica(self.toptica_voltage.get(), self.toptica_current.get())
        self.get_frequency()

    def get_frequency(self):
        _, freq, _ = self.wand_server.get_freq(TOPTICA_TO_WAND_NAMES[self.laser_name])

        self.frequency.push(freq)
        self.detuning.push(freq - self.nominal_setpoint)

    def set_toptica(self, new_voltage, new_current):
        if new_voltage > 0:
            self.laser.dl.pc.voltage_set.set(new_voltage)

        if new_current > 0:
            self.laser.dl.cc.current_set.set(1e3 * new_current)


ScanTopticaWithWavemeter = make_fragment_scan_exp(ScanTopticaWithWavemeterFrag)
