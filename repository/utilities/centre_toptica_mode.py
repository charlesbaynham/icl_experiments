import logging
import time
from math import floor

from artiq.experiment import EnumerationValue
from artiq.master.scheduler import Scheduler
from artiq.master.worker_impl import CCB
from artiq_influx_generic import InfluxController
from ndscan.experiment import ExpFragment
from ndscan.experiment import make_fragment_scan_exp
from ndscan.experiment.parameters import BoolParam
from ndscan.experiment.parameters import BoolParamHandle
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

    laser_name: str = None  # type: ignore[assignment]

    def build_fragment(self, laser_name: str | None = None):
        self.set_default_scheduling(pipeline_name="wand")

        toptica_lasers = list(constants.TOPTICA_TO_WAND_NAMES.keys())

        if laser_name is not None:
            self.laser_name = laser_name

        if self.laser_name is None:
            # Allow the user to choose the laser by subclassing this Fragment if
            # they want. Otherwise make an argument
            self.setattr_argument(
                "laser_name",
                EnumerationValue(toptica_lasers, default=toptica_lasers[0]),  # type: ignore[arg-type]
            )
            if self.laser_name is None:
                # We are in build()
                self.laser_name = toptica_lasers[0]

        self.setattr_fragment("wand_steering", WandSteering)
        self.wand_steering: WandSteering

        self.setattr_device("wand_server")
        self.wand_server: WANDControlInterface

        self.setattr_device("ccb")
        self.ccb: CCB

        self.setattr_device("scheduler")
        self.scheduler: Scheduler

        self.setattr_device("influx_logger")
        self.influx_logger: InfluxController

        # Parameter for target detuning from WAND reference
        self.setattr_param(
            "target_detuning",
            FloatParam,
            default=0.0,
            description="Target detuning from WAND reference frequency",
            unit="MHz",
        )
        self.target_detuning: FloatParamHandle

        # Tolerance for determining whether the laser is on the correct mode
        self.setattr_param(
            "mode_check_tolerance",
            FloatParam,
            default=constants.DEFAULT_MODE_CENTRING_SETTINGS[
                self.laser_name
            ].mode_check_tolerance,
            description="Tolerance for correct mode detection",
            unit="GHz",
            min=0.0,
        )
        self.mode_check_tolerance: FloatParamHandle

        # Safety parameters for current scanning
        self.setattr_param(
            "min_safe_current",
            FloatParam,
            default=0.0,
            description="Minimum safe laser diode current",
            unit="mA",
            min=0.0,
        )
        self.min_safe_current: FloatParamHandle

        self.setattr_param(
            "max_safe_current",
            FloatParam,
            default=constants.DEFAULT_MODE_CENTRING_SETTINGS[
                self.laser_name
            ].max_current,
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
            default=constants.DEFAULT_MODE_CENTRING_SETTINGS[
                self.laser_name
            ].current_step,
            description="Current increment for scanning to find mode boundaries",
            unit="mA",
            min=0.01e-3,
        )
        self.current_step: FloatParamHandle

        self.setattr_param(
            "initial_restore_jump_size",
            FloatParam,
            default=100e-6,
            description="Initial current jump size for mode restoration (will increase geometrically)",
            unit="mA",
            min=1e-6,
        )
        self.initial_restore_jump_size: FloatParamHandle

        self.setattr_param(
            "max_restore_jump_size",
            FloatParam,
            default=constants.DEFAULT_MODE_CENTRING_SETTINGS[
                self.laser_name
            ].max_restore_jump_size,
            description="Maximum current jump size for mode restoration",
            unit="mA",
            min=0,
        )
        self.max_restore_jump_size: FloatParamHandle

        self.setattr_param(
            "current_tolerance",
            FloatParam,
            default=constants.DEFAULT_MODE_CENTRING_SETTINGS[
                self.laser_name
            ].fractional_current_tolerance,
            description="Maximum allowed current drift as fraction of mode-hop-free range",
            min=0.01,
            max=0.5,
        )
        self.current_tolerance: FloatParamHandle

        self.setattr_param(
            "mode_position_fraction",
            FloatParam,
            default=constants.DEFAULT_MODE_CENTRING_SETTINGS[
                self.laser_name
            ].target_position,
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

    def is_on_correct_mode(self, target_detuning) -> bool:
        """Check if the laser is on the correct mode.

        Returns:
            True if within `mode_check_tolerance` GHz of target, False otherwise
        """
        tolerance = self.mode_check_tolerance.get()
        current_detuning = self.get_current_detuning()

        return abs(current_detuning - target_detuning) < tolerance

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

    def get_max_current(self) -> float:
        """Get the maximum laser diode current in A.

        Returns:
            Maximum current in A
        """
        return self.laser.dl.cc.current_clip.get() * 1e-3

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
        self,
        target_current: float,
        target_detuning: float,
        max_attempts: int = 20,
    ) -> bool:
        """Restore the laser to the correct mode by jumping current down and back up.

        Uses geometric progression: starts with small jumps and doubles the magnitude
        on each failed attempt up to the maximum jump size.

        Args:
            target_current: The target current to return to in A
            max_attempts: Maximum number of restore attempts
            target_detuning: The target detuning.

        Returns:
            True if successfully restored, False if failed after max_attempts
        """
        settle_time = 3.0

        initial_jump = self.initial_restore_jump_size.get()
        max_jump = abs(self.max_restore_jump_size.get())
        max_current = self.get_max_current()

        # Start with positive jumps
        direction = 1

        for attempt in range(1, max_attempts + 1):
            if self.is_on_correct_mode(target_detuning=target_detuning):
                logger.info("Mode restored successfully on attempt %d", attempt)
                return True

            # Calculate jump size using geometric progression: initial * 2^(attempt-1)
            # Clamped to max_jump
            jump_magnitude = min(
                initial_jump * (2 ** (floor((attempt - 1) / 2))), max_jump
            )

            # Alternate direction on each attempt
            current_direction = direction if attempt % 2 == 1 else -direction
            next_jump = current_direction * jump_magnitude

            logger.warning(
                "Mode restore attempt %d/%d with jump %.3f mA",
                attempt,
                max_attempts,
                1e3 * next_jump,
            )
            logger.debug("Jump magnitude: %.3f µA", 1e6 * jump_magnitude)

            # Jump current
            target = target_current + next_jump
            if target > max_current:
                target = max_current - 10e-6
                logger.debug("Clamped jump to max current limit")

            self.set_current(target)
            time.sleep(1.0)

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

        # Open a connection to the Toptica
        self.raw_dlcpro.open()

        # Store start time for relative timestamps
        self.start_time = time.time()

        # Create applets for real-time plotting
        self.set_dataset("current_history", [], broadcast=True)
        self.set_dataset("frequency_history", [], broadcast=True)
        self.set_dataset("timestamp_history", [], broadcast=True)
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

        logger.info("Starting mode centring for laser: %s", self.laser_name)

        # -2. Disable WAND locking to prevent interference
        self.wand_server.unlock(wand_laser_name, name="")

        # -1. Disable ARC if it is enabled to prevent external steering
        initial_arc_enabled = self.get_arc_state()
        if initial_arc_enabled:
            logger.info("Disabling ARC for mode centring")
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
            if not self.is_on_correct_mode(target_detuning=self.target_detuning.get()):
                raise RuntimeError(
                    "Laser is not on the correct mode. Please manually set the laser "
                    "to the correct mode before running this experiment."
                )

            max_iterations = 10
            for iteration in range(max_iterations):
                self.scheduler.pause()  # type: ignore[attr-defined]
                logger.info("Starting mode centring iteration %d", iteration + 1)

                # 1. Record the starting voltage, current and detuning
                i_start = self.get_current()
                v_start = self.get_voltage()
                f_start = self.get_current_detuning()
                logger.info(
                    "Starting current: %.3f mA, voltage: %.3f V, detuning: %.3f MHz",
                    1e3 * i_start,
                    v_start,
                    1e-6 * f_start,
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
                    self.scheduler.pause()  # type: ignore[attr-defined]
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

                if not self.restore_correct_mode(i_start, f_start):
                    raise RuntimeError(
                        "Failed to restore correct mode after upward scan"
                    )

                # 6-7. Decrease current until mode hop, record i_bottom
                logger.info("Scanning current downward to find lower mode boundary")
                i_current = i_start
                previous_detuning = self.get_current_detuning()
                i_bottom = i_start

                while True:
                    self.scheduler.pause()  # type: ignore[attr-defined]
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

                # 9.1. Jump to original current and restore mode if necessary
                logger.info("Setting current to initial: %.3f mA", 1e3 * i_start)
                self.set_current(i_start)
                time.sleep(1.0)

                if not self.restore_correct_mode(i_start, f_start):
                    raise RuntimeError(
                        "Failed to restore correct mode at start current"
                    )

                # 9.2. Jump to target current and restore mode if necessary
                logger.info("Setting current to target: %.3f mA", 1e3 * i_target)
                self.set_current(i_target)
                time.sleep(1.0)

                if not self.restore_correct_mode(i_target, f_start):
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
                current_drift = abs(i_final - i_target)
                max_allowed_drift = self.current_tolerance.get() * mode_hop_free_range

                logger.info(
                    "Current drift: %.3f mA, max allowed: %.3f mA",
                    1e3 * current_drift,
                    1e3 * max_allowed_drift,
                )

                if current_drift <= max_allowed_drift:
                    logger.info("Mode successfully centred!")

                    # Log success to InfluxDB
                    self.influx_logger.write(  # type: ignore[arg-type]
                        tags={
                            "type": "CentreTopticaMode",
                            "laser": self.laser_name,
                            "rid": self.scheduler.rid,  # type: ignore[attr-defined]
                        },
                        fields={
                            "i_start": initial_current,
                            "i_bottom": i_bottom,
                            "i_top": i_top,
                            "i_target": i_target,
                            "i_final": i_final,
                            "mode_hop_free_range": mode_hop_free_range,
                            "v_initial": v_start,
                            "v_final": self.get_voltage(),
                            "target_detuning": target_detuning,
                            "final_detuning": self.get_current_detuning(),
                            "iterations": iteration + 1,
                        },
                    )

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
                    "Mode centring did not converge after %d iterations",
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

            logger.info("Leaving feed-forward on, regardless of original state")
            self.set_feedforward(True)

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


class CentreAllTopticaModesFrag(ExpFragment):
    """Centre all Toptica laser modes within their mode-hop free ranges.

    This experiment iterates through all Toptica lasers defined in
    TOPTICA_TO_WAND_NAMES and centres each one by creating a subfragment
    for each laser and running the centring algorithm.
    """

    def build_fragment(self):
        self.set_default_scheduling(pipeline_name="wand")

        # Create a subfragment for each Toptica laser
        self.laser_fragments: dict[str, CentreTopticaModeFrag] = {}
        self.laser_enabled_handles: dict[str, BoolParamHandle] = {}
        for laser_name in constants.TOPTICA_TO_WAND_NAMES.keys():
            fragment_attr_name = f"centre_{laser_name}"
            self.laser_fragments[laser_name] = self.setattr_fragment(  # type: ignore
                fragment_attr_name, CentreTopticaModeFrag, laser_name=laser_name
            )

            # Add an enable parameter for each laser
            param_attr_name = f"enable_{laser_name}"
            self.laser_enabled_handles[laser_name] = self.setattr_param(  # type: ignore
                param_attr_name,
                BoolParam,
                default=True,
                description=f"Enable centring for {laser_name}",
            )

    def run_once(self):
        """Centre each Toptica laser in sequence."""
        for laser_name, fragment in self.laser_fragments.items():
            enabled = self.laser_enabled_handles[laser_name].get()

            if enabled:
                logger.info("Centring laser: %s", laser_name)
                fragment.run_once()
                logger.info("Completed centring laser: %s", laser_name)


CentreTopticaMode = make_fragment_scan_exp(CentreTopticaModeFrag)
CentreAllTopticaModes = make_fragment_scan_exp(CentreAllTopticaModesFrag)
