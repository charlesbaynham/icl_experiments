import logging

from artiq.experiment import EnumerationValue
from ndscan.experiment import ExpFragment
from ndscan.experiment import make_fragment_scan_exp
from ndscan.experiment.parameters import BoolParam
from ndscan.experiment.parameters import BoolParamHandle
from ndscan.experiment.parameters import FloatParam
from ndscan.experiment.parameters import FloatParamHandle
from ndscan.experiment.result_channels import FloatChannel
from toptica_wrapper import TopticaDLCPro
from wand.server import ControlInterface as WANDControlInterface

from repository.lib import constants

logger = logging.getLogger(__name__)

TOPTICA_TO_WAND_NAMES = {
    "toptica_461": "461",
    "toptica_679": "679",
    "toptica_707": "707",
    "toptica_689": "689",
    "toptica_698": "698",
    "toptica_487": "487",
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

        self.setattr_param(
            "cutoff_detuning",
            FloatParam,
            default=-1,
            description="Max detuning to record (-1 = no cutoff)",
            unit="MHz",
        )
        self.cutoff_detuning: FloatParamHandle

        self.setattr_param(
            "disable_feedforward",
            BoolParam,
            default=False,
            description="Disable laser feedforward during scan",
        )
        self.disable_feedforward: BoolParamHandle

        self.setattr_param(
            "restore_settings",
            BoolParam,
            default=True,
            description="Restore initial settings after scan",
        )
        self.restore_settings: BoolParamHandle

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

        # Record the initial current and voltage
        self.initial_piezo_voltage = self.laser.dl.pc.voltage_set.get()
        self.initial_current = self.laser.dl.cc.current_set.get()

        # Disable feedforward if requested
        self.initial_feedforward = self.get_feedforward()
        if self.disable_feedforward.get():
            self.set_feedforward(False)

        return super().host_setup()

    def set_feedforward(self, enabled: bool):
        self.laser.dl.cc.feedforward_enabled.set(enabled)

    def get_feedforward(self):
        return bool(self.laser.dl.cc.feedforward_enabled.get())

    def run_once(self):
        self.set_toptica(self.toptica_voltage.get(), self.toptica_current.get())
        self.get_frequency()

    def get_frequency(self):
        _, freq, _ = self.wand_server.get_freq(TOPTICA_TO_WAND_NAMES[self.laser_name])
        detuning = freq - self.nominal_setpoint

        if self.cutoff_detuning.get() > 0:
            if abs(detuning) > self.cutoff_detuning.get():
                detuning = float("nan")

        self.frequency.push(freq)
        self.detuning.push(detuning)

    def set_toptica(self, new_voltage, new_current):
        if new_voltage > 0:
            self.laser.dl.pc.voltage_set.set(new_voltage)

        if new_current > 0:
            self.laser.dl.cc.current_set.set(1e3 * new_current)

    def host_cleanup(self):
        super().host_cleanup()

        if self.restore_settings.get():
            logger.warning(
                "Restoring initial laser settings:\n"
                f"voltage={self.initial_piezo_voltage} V,\n"
                f"current={self.initial_current} mA,\n"
                f"feedforward={'on' if self.initial_feedforward else 'off'}"
            )

            # Restore initial voltage and current
            self.laser.dl.pc.voltage_set.set(self.initial_piezo_voltage)
            self.laser.dl.cc.current_set.set(self.initial_current)

        # Turn feedforward back on if we turned it off
        if self.disable_feedforward.get():
            self.set_feedforward(self.initial_feedforward)


ScanTopticaWithWavemeter = make_fragment_scan_exp(ScanTopticaWithWavemeterFrag)
