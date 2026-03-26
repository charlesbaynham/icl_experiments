import logging

from gaio_laser_driver.driver import GAIO
from ndscan.experiment import ExpFragment
from ndscan.experiment import make_fragment_scan_exp
from ndscan.experiment.parameters import BoolParam
from ndscan.experiment.parameters import BoolParamHandle
from ndscan.experiment.parameters import FloatParam
from ndscan.experiment.parameters import FloatParamHandle
from ndscan.experiment.result_channels import FloatChannel
from wand.server import ControlInterface as WANDControlInterface

from repository.lib import constants

logger = logging.getLogger(__name__)


class ScanGAOWithWavemeterFrag(ExpFragment):
    """
    Scan a GAO-board laser and measure it with WAND

    Note: does not use the core.
    """

    laser_name = None

    def build_fragment(self) -> None:
        self.setattr_device("wand_server")
        self.wand_server: WANDControlInterface

        list(constants.TOPTICA_TO_WAND_NAMES.keys())

        self.setattr_param(
            "voltage",
            FloatParam,
            default=1.0,
            min=0.0,
            max=4.0,
            description="New voltage",
            unit="V",
        )
        self.voltage: FloatParamHandle

        self.setattr_param(
            "restore_settings",
            BoolParam,
            description="Restore initial laser settings after scan",
            default=True,
        )
        self.restore_settings: BoolParamHandle

        self.frequency: FloatChannel
        self.detuning: FloatChannel

    def host_setup(self):
        # Get the laser controller and open a connection to it. This is done in
        # host_setup since the user can choose which laser they're using
        self.gao_board_688: GAIO = self.get_device("gaio_wand_driver_688")

        # Get the laser's nominal setpoint
        self.nominal_setpoint = constants.WAND_SETPOINTS_87["688"][0]

        # Record the initial current and voltage
        self.initial_voltage = self.gao_board_688.query_get_pzt_voltage()

        return super().host_setup()

    def run_once(self):
        self.set_voltage(self.voltage.get())
        self.get_frequency()

    def get_frequency(self):
        _, freq, _ = self.wand_server.get_freq("688")
        detuning = freq - self.nominal_setpoint

        if self.cutoff_detuning.get() > 0:
            if abs(detuning) > self.cutoff_detuning.get():
                detuning = float("nan")

        self.frequency.push(freq)
        self.detuning.push(detuning)

    def set_voltage(self, new_voltage):
        if new_voltage > 0:
            self.gao_board_688.query_set_pzt_voltage(new_voltage)

    def host_cleanup(self):
        super().host_cleanup()

        if self.restore_settings.get():
            logger.warning(
                "Restoring initial laser settings:\n"
                f"voltage={self.initial_voltage} V,\n"
            )

            # Restore initial voltage
            self.set_voltage(self.initial_voltage)


ScanGAOWithWavemeter = make_fragment_scan_exp(ScanGAOWithWavemeterFrag)
