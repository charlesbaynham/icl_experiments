import logging
import time

from artiq.experiment import EnumerationValue
from artiq.master.scheduler import Scheduler
from artiq.master.worker_impl import CCB
from ndscan.experiment import ExpFragment
from ndscan.experiment import make_fragment_scan_exp
from ndscan.experiment.parameters import FloatParam
from ndscan.experiment.parameters import FloatParamHandle
from toptica_wrapper.driver import TopticaDLCPro
from wand.server import ControlInterface as WANDControlInterface
from wand.tools import WLMMeasurementStatus

from repository.lib import constants
from repository.lib.fragments.wand_steering import WandSteering

logger = logging.getLogger(__name__)


class CentreTopticaModeFrag(ExpFragment):
    """Centre a Toptica laser mode within its mode-hop free range.

    This experiment centres the mode of a Toptica laser so that it is at a
    specified position within its mode-hop free range. The laser must already
    be lasing on the correct mode before running this experiment.

    Algorithm:
        -1. Disable ARC if enabled to prevent external steering
        0. Confirm that the laser is on the correct mode (within 15 GHz of setpoint)
        1. Record the starting voltage and current
        2. Turn off feed-forward
        3. Increase current until mode hop occurs
        4. Record the current just before the mode-hop as I_top
        5. Jump back to starting position and restore lasing on the correct mode
           if necessary by jumping current down and back up
        6. Decrease current until mode hop occurs
        7. Record the current just before the mode-hop as I_bottom
        8. Calculate the target current based on mode_position_fraction parameter
        9. Jump to this current and restore lasing on the correct mode if necessary
        10. Turn on feed-forward if it was originally enabled
        11. Steer the wavelength to the frequency setpoint using WAND
        12. Check the current drift. If too large, iterate from step 1
        13. Re-enable ARC if it was originally enabled
    """

    laser_name = None

    def build_fragment(self):
        self.set_default_scheduling(pipeline_name="wand")

        toptica_lasers = list(constants.TOPTICA_TO_WAND_NAMES.keys())

        if self.laser_name is None:
            # Allow the user to choose the laser by subclassing this Fragment if
            # they want. Otherwise make an argument
            self.setattr_argument(
                "laser_name",
                EnumerationValue(toptica_lasers, default=toptica_lasers[0]),
            )
            self.laser_name: str

        self.setattr_fragment("wand_steering", WandSteering)
        self.wand_steering: WandSteering

        self.setattr_device("wand_server")
        self.wand_server: WANDControlInterface

        self.setattr_device("ccb")
        self.ccb: CCB

        self.setattr_device("scheduler")
        self.scheduler: Scheduler

        # Parameter for target detuning from WAND reference
        self.setattr_param(
            "target_detuning",
            FloatParam,
            default=0.0,
            description="Target detuning from WAND reference frequency",
            unit="MHz",
        )
        self.target_detuning: FloatParamHandle

        # Safety parameters for current scanning
        self.setattr_param(
            "min_safe_current",
            FloatParam,
            default=80.0e-3,
            description="Minimum safe laser diode current",
            unit="mA",
            min=0.0,
        )
        self.min_safe_current: FloatParamHandle

        self.setattr_param(
            "max_safe_current",
            FloatParam,
            default=150.0e-3,
            description="Maximum safe laser diode current",
            unit="mA",
            min=0.0,
        )
        self.max_safe_current: FloatParamHandle

        # Mode detection and scanning parameters
        self.setattr_param(
            "mode_hop_threshold",
            FloatParam,
            default=1e9,
            description="Frequency change threshold to consider a mode hop",
            unit="GHz",
        )
        self.mode_hop_threshold: FloatParamHandle

        self.setattr_param(
            "current_step",
            FloatParam,
            default=0.1e-3,
            description="Current increment for scanning to find mode boundaries",
            unit="mA",
            min=0.01e-3,
        )
        self.current_step: FloatParamHandle

        self.setattr_param(
            "restore_jump_size",
            FloatParam,
            default=-5.0e-3,
            description="Current jump size for mode restoration (negative to jump down)",
            unit="mA",
        )
        self.restore_jump_size: FloatParamHandle

        self.setattr_param(
            "current_tolerance",
            FloatParam,
            default=0.1,
            description="Maximum allowed current drift as fraction of mode-hop-free range",
            min=0.01,
            max=0.5,
        )
        self.current_tolerance: FloatParamHandle

        self.setattr_param(
            "mode_position_fraction",
            FloatParam,
            default=0.5,
            description="Target position within mode-hop-free range (0=bottom, 1=top)",
            min=0.0,
            max=1.0,
        )
        self.mode_position_fraction: FloatParamHandle

        self.setattr_param(
            "max_steer_in_one_go",
            FloatParam,
            default=5e9,
            description="Maximum frequency change per steering iteration",
            unit="GHz",
            min=0.1e9,
            max=50e9,
        )
        self.max_steer_in_one_go: FloatParamHandle

    def host_setup(self):
        super().host_setup()

        self.toptica: TopticaDLCPro = self.get_device(self.laser_name)
        self.raw_dlcpro = self.toptica.get_dlcpro()
        self.laser = self.toptica.get_laser()

        # Open a connection to the Toptica
        self.raw_dlcpro.open()

        # Initialize datasets for debugging
        self.set_dataset("current_history", [], broadcast=True)
        self.set_dataset("frequency_history", [], broadcast=True)
        self.set_dataset("timestamp_history", [], broadcast=True)

        # Store start time for relative timestamps
        self.start_time = time.time()

    def record_measurement(self, current: float, frequency: float):
        """Record current and frequency measurement to datasets for debugging.

        Args:
            current: Laser diode current in A
            frequency: Laser frequency detuning in Hz
        """
        timestamp = time.time() - self.start_time
        self.append_to_dataset("current_history", current)
        self.append_to_dataset("frequency_history", frequency)
        self.append_to_dataset("timestamp_history", timestamp)

    def get_current_detuning(self) -> float:
        """Get the current laser detuning from WAND reference in Hz.

        Returns:
            Laser frequency detuning in Hz

        Raises:
            RuntimeError: If valid frequency measurement cannot be obtained
        """
        max_attempts = 10
        for attempt in range(1, max_attempts + 1):
            status, detuning, _ = self.wand_server.get_freq(  # type: ignore[misc]
                constants.TOPTICA_TO_WAND_NAMES[self.laser_name], offset_mode=True
            )

            if status == WLMMeasurementStatus.OKAY:
                # Record the measurement
                current = self.get_current()
                self.record_measurement(current, detuning)
                return detuning

            logger.warning(
                "WAND measurement status: %s (attempt %d/%d)",
                status,
                attempt,
                max_attempts,
            )

            if attempt < max_attempts:
                time.sleep(0.1)

        raise RuntimeError(
            "Failed to get valid frequency measurement from WAND after %d attempts. "
            "Last status: %s",
            max_attempts,
            status,
        )

    def is_on_correct_mode(self) -> bool:
        """Check if the laser is on the correct mode.

        Returns:
            True if within 15 GHz of target, False otherwise
        """
        tolerance = 15e9
        current_detuning = self.get_current_detuning()
        target = self.target_detuning.get()
        return abs(current_detuning - target) < tolerance

    def get_current(self) -> float:
        """Get the current laser diode current in A.

        Returns:
            Current in A
        """
        current_ma = self.laser.dl.cc.current_set.get()
        return current_ma * 1e-3

    def set_current(self, current: float):
        """Set the laser diode current in A.

        Args:
            current: Target current in A
        """
        current_ma = current * 1e3
        logger.debug("Setting current to %.3f mA", current_ma)
        self.laser.dl.cc.current_set.set(current_ma)

    def get_voltage(self) -> float:
        """Get the current piezo voltage in V.

        Returns:
            Piezo voltage in V
        """
        return self.laser.dl.pc.voltage_set.get()

    def set_voltage(self, voltage: float):
        """Set the piezo voltage in V.

        Args:
            voltage: Target voltage in V
        """
        self.laser.dl.pc.voltage_set.set(voltage)

    def get_feedforward_enabled(self) -> bool:
        """Get the current feed-forward state.

        Returns:
            True if feed-forward is enabled, False otherwise
        """
        return bool(self.laser.dl.cc.feedforward_enabled.get())

    def set_feedforward(self, enabled: bool):
        """Set the feed-forward state.

        Args:
            enabled: True to enable feed-forward, False to disable
        """
        self.laser.dl.cc.feedforward_enabled.set(enabled)

    def detect_mode_hop(self, previous_detuning: float, threshold: float) -> bool:
        """Detect if a mode hop has occurred.

        Args:
            previous_detuning: The previous frequency measurement in Hz
            threshold: Frequency change threshold to consider a mode hop in Hz

        Returns:
            True if mode hop detected, False otherwise
        """
        current_detuning = self.get_current_detuning()
        return abs(current_detuning - previous_detuning) > threshold

    def restore_correct_mode(
        self, target_current: float, max_attempts: int = 10
    ) -> bool:
        """Restore the laser to the correct mode by jumping current down and back up.

        Args:
            target_current: The target current to return to in A
            max_attempts: Maximum number of restore attempts

        Returns:
            True if successfully restored, False if failed after max_attempts
        """
        jump_size = self.restore_jump_size.get()
        settle_time = 5.0

        for attempt in range(1, max_attempts + 1):
            if self.is_on_correct_mode():
                if attempt > 1:
                    logger.info("Mode restored successfully on attempt %d", attempt)
                return True

            logger.warning("Mode restore attempt %d/%d", attempt, max_attempts)

            # Jump current down
            self.set_current(target_current + jump_size)
            time.sleep(0.1)

            # Jump back to target
            self.set_current(target_current)
            time.sleep(settle_time)

        logger.error("Failed to restore mode after %d attempts", max_attempts)
        return False

    def check_current_within_limits(self, current: float):
        """Check if a current value is within safe operating limits.

        Args:
            current: The current to check in A

        Raises:
            RuntimeError: If current is outside safe limits
        """
        min_safe = self.min_safe_current.get()
        max_safe = self.max_safe_current.get()

        if current > max_safe:
            logger.error(
                "Current %.3f mA exceeds max safe limit of %.3f mA",
                1e3 * current,
                1e3 * max_safe,
            )
            raise RuntimeError("Current exceeds maximum safe limit")

        if current < min_safe:
            logger.error(
                "Current %.3f mA below min safe limit of %.3f mA",
                1e3 * current,
                1e3 * min_safe,
            )
            raise RuntimeError("Current below minimum safe limit")

    def set_arc_state(self, enabled: bool):
        """Set the ARC (external input) state.

        Args:
            enabled: True to enable ARC, False to disable
        """
        self.laser.dl.pc.external_input.enabled.set(enabled)

    def get_arc_state(self) -> bool:
        """Get the current ARC (external input) state.

        Returns:
            True if ARC is enabled, False otherwise
        """
        return bool(self.laser.dl.pc.external_input.enabled.get())

    def set_FALC(self, main=False, unlim=False):
        logger.info("Setting FALC: main=%s, unlim=%s", main, unlim)
        falc = self.toptica.get_falc()

        falc.main.enabled.set(main)
        falc.unlim.enabled.set(unlim)

    def get_FALC(self):
        falc = self.toptica.get_falc()
        return bool(falc.main.enabled.get()), bool(falc.unlim.enabled.get())

    def run_once(self):
        """Execute the mode centring algorithm."""
        # Create applets for real-time plotting
        cmd_current = (
            "${artiq_applet}plot_xy current_history --x timestamp_history "
            "--title 'Toptica Current vs Time'"
        )
        self.ccb.issue("create_applet", "Toptica Current vs Time", cmd_current)

        cmd_freq = (
            "${artiq_applet}plot_xy frequency_history --x timestamp_history "
            "--title 'Toptica Frequency vs Time'"
        )
        self.ccb.issue("create_applet", "Toptica Frequency vs Time", cmd_freq)

        wand_laser_name = constants.TOPTICA_TO_WAND_NAMES[self.laser_name]
        current_step = self.current_step.get()
        mode_hop_threshold = self.mode_hop_threshold.get()

        # -1. Disable ARC if it is enabled to prevent external steering
        initial_arc_enabled = self.get_arc_state()
        if initial_arc_enabled:
            logger.info("Disabling ARC for mode centering")
            self.set_arc_state(False)

        # Check initial FALC state (if present)
        initial_falc_state = None
        try:
            initial_falc_state = self.get_FALC()
            logger.info(
                "Initial FALC state - main: %s, unlim: %s",
                initial_falc_state[0],
                initial_falc_state[1],
            )
        except TypeError:
            logger.info("No FALC present for this laser")

        # Record initial state to be restored later
        initial_feedforward = self.get_feedforward_enabled()
        succeeded = False
        initial_current = self.get_current()
        initial_voltage = self.get_voltage()

        try:
            # 0. Confirm that the laser is on the correct mode
            if not self.is_on_correct_mode():
                raise RuntimeError(
                    "Laser is not on the correct mode. Please manually set the laser "
                    "to the correct mode before running this experiment."
                )

            max_iterations = 10
            for iteration in range(max_iterations):
                self.scheduler.pause()
                logger.info("Starting mode centering iteration %d", iteration + 1)

                # 1. Record the starting voltage and current
                i_start = self.get_current()
                v_start = self.get_voltage()
                logger.info(
                    "Starting current: %.3f mA, voltage: %.3f V",
                    1e3 * i_start,
                    v_start,
                )

                # 2. Turn off feed-forward
                logger.info("Disabling feed-forward")
                self.set_feedforward(False)

                # 3-4. Increase current until mode hop, record i_top
                logger.info("Scanning current upward to find upper mode boundary")
                i_current = i_start
                previous_detuning = self.get_current_detuning()
                i_top = i_start

                while True:
                    self.scheduler.pause()
                    i_current += current_step

                    self.check_current_within_limits(i_current)

                    self.set_current(i_current)
                    time.sleep(0.2)

                    if self.detect_mode_hop(previous_detuning, mode_hop_threshold):
                        logger.info("Mode hop detected at %.3f mA", 1e3 * i_current)
                        i_top = i_current - current_step
                        break

                    previous_detuning = self.get_current_detuning()
                    i_top = i_current

                logger.info("Upper mode boundary: %.3f mA", 1e3 * i_top)

                # 5. Jump back to starting position and restore mode if necessary
                logger.info("Returning to starting current")
                self.set_current(i_start)
                time.sleep(1.0)

                if not self.restore_correct_mode(i_start):
                    raise RuntimeError(
                        "Failed to restore correct mode after upward scan"
                    )

                # 6-7. Decrease current until mode hop, record i_bottom
                logger.info("Scanning current downward to find lower mode boundary")
                i_current = i_start
                previous_detuning = self.get_current_detuning()
                i_bottom = i_start

                while True:
                    self.scheduler.pause()
                    i_current -= current_step

                    self.check_current_within_limits(i_current)

                    self.set_current(i_current)
                    time.sleep(0.2)

                    if self.detect_mode_hop(previous_detuning, mode_hop_threshold):
                        logger.info("Mode hop detected at %.3f mA", 1e3 * i_current)
                        i_bottom = i_current + current_step
                        break

                    previous_detuning = self.get_current_detuning()
                    i_bottom = i_current

                logger.info("Lower mode boundary: %.3f mA", 1e3 * i_bottom)

                # 8. Calculate the target current
                mode_hop_free_range = i_top - i_bottom
                i_target = (
                    i_bottom + self.mode_position_fraction.get() * mode_hop_free_range
                )
                logger.info(
                    "Mode-hop free range: %.3f mA, target current: %.3f mA",
                    1e3 * mode_hop_free_range,
                    1e3 * i_target,
                )

                # 9. Jump to target current and restore mode if necessary
                logger.info("Setting current to target: %.3f mA", 1e3 * i_target)
                self.set_current(i_target)
                time.sleep(1.0)

                if not self.restore_correct_mode(i_target):
                    raise RuntimeError(
                        "Failed to restore correct mode at target current"
                    )

                # 10. Turn on feed-forward if it was originally enabled
                if initial_feedforward:
                    logger.info("Enabling feed-forward")
                    self.set_feedforward(True)

                # 11. Steer the wavelength to the frequency setpoint using WAND
                logger.info("Steering laser to target frequency using WAND")
                target_detuning = self.target_detuning.get()
                current_detuning = self.get_current_detuning()
                required_steer = target_detuning - current_detuning
                max_steer = self.max_steer_in_one_go.get()

                # Clamp the steering to max_steer_in_one_go
                if abs(required_steer) > max_steer:
                    clamped_steer = max_steer if required_steer > 0 else -max_steer
                    actual_target = current_detuning + clamped_steer
                    logger.info(
                        "Steering limited: required %.3f GHz, clamping to %.3f GHz",
                        1e-9 * required_steer,
                        1e-9 * clamped_steer,
                    )
                else:
                    actual_target = target_detuning
                    logger.info("Steering by %.3f GHz", 1e-9 * required_steer)

                self.wand_steering.steer_wand(
                    laser=wand_laser_name,
                    offset=actual_target,
                    timeout=30.0,
                    required_accuracy=2e6,  # 2 MHz accuracy
                    leave_locked=False,
                )

                # 12. Check if we need to iterate
                i_final = self.get_current()
                current_drift = abs(i_final - i_start)
                max_allowed_drift = self.current_tolerance.get() * mode_hop_free_range

                logger.info(
                    "Current drift: %.3f mA, max allowed: %.3f mA",
                    1e3 * current_drift,
                    1e3 * max_allowed_drift,
                )

                if current_drift <= max_allowed_drift:
                    logger.info("Mode successfully centered!")
                    succeeded = True
                    break

                logger.warning(
                    "Current drifted too much, iterating (attempt %d/%d)",
                    iteration + 1,
                    max_iterations,
                )

            else:
                # Loop completed without break (max iterations reached)
                logger.warning(
                    "Mode centering did not converge after %d iterations",
                    max_iterations,
                )
                raise RuntimeError(
                    "Failed to center mode after %d iterations" % max_iterations
                )

        finally:
            # 13. Re-enable ARC & feedforward if they were originally enabled
            if initial_arc_enabled:
                logger.info("Re-enabling ARC")
                self.set_arc_state(True)

            logger.info("Restoring initial feed-forward state: %s", initial_feedforward)
            self.set_feedforward(initial_feedforward)

            # Restore initial FALC state if it was present
            if initial_falc_state is not None:
                logger.info(
                    "Restoring FALC state - main: %s, unlim: %s",
                    initial_falc_state[0],
                    initial_falc_state[1],
                )
                self.set_FALC(main=initial_falc_state[0], unlim=initial_falc_state[1])

            # Restore original current and voltage if we failed
            if not succeeded:
                logger.info("Restoring initial current and voltage")
                self.set_current(initial_current)
                self.set_voltage(initial_voltage)

            # Close the connection
            self.raw_dlcpro.close()


CentreTopticaMode = make_fragment_scan_exp(CentreTopticaModeFrag)
