"""Walk the 461 piezo until the wand detuning is within WAND-lock capture,
then hand off to the WAND lock at the target setpoint.

For recovering a 461 parked tens of GHz off (2026-07-04: +46 GHz after an
ARC-rail episode), where the WAND lock's capture range (5 GHz) can't reach.
Measures the local GHz/V slope, walks in bounded steps, re-estimating as it
goes; hands off to WandSteering once within ``handoff_range``.
"""

import logging
import time

from ndscan.experiment import ExpFragment
from ndscan.experiment import make_fragment_scan_exp
from ndscan.experiment.parameters import FloatParam
from ndscan.experiment.parameters import FloatParamHandle
from toptica_wrapper.driver import TopticaDLCPro
from wand.tools import WLMMeasurementStatus

from repository.lib.fragments.wand_steering import WandSteering

logger = logging.getLogger(__name__)

VOLT_MIN = 5.0
VOLT_MAX = 135.0
MAX_STEP_V = 3.0
MAX_STEPS = 60


class Steer461PiezoToWandFrag(ExpFragment):
    def build_fragment(self):
        self.set_default_scheduling(pipeline_name="wand")

        self.setattr_fragment("wand_steering", WandSteering)
        self.wand_steering: WandSteering

        self.setattr_device("wand_server")

        self.setattr_param(
            "target_offset",
            FloatParam,
            "Final WAND lock setpoint",
            default=12.4e6,
            unit="MHz",
        )
        self.target_offset: FloatParamHandle

        self.setattr_param(
            "handoff_range",
            FloatParam,
            "Hand off to the WAND lock inside this detuning",
            default=1.0e9,
            unit="MHz",
        )
        self.handoff_range: FloatParamHandle

        self.toptica_461: TopticaDLCPro = self.get_device("toptica_461")

    def host_setup(self):
        super().host_setup()
        self.raw_dlcpro = self.toptica_461.get_dlcpro()

    def _read_offset(self):
        for _ in range(10):
            status, offset, _ = self.wand_server.get_freq(
                laser="461", offset_mode=True, age=1
            )
            if status == WLMMeasurementStatus.OKAY:
                return offset
            time.sleep(2)
        raise RuntimeError("wand could not measure the 461")

    def run_once(self):
        self.raw_dlcpro.open()
        laser = self.toptica_461.get_laser()
        pc = laser.dl.pc

        if pc.external_input.enabled.get():
            pc.external_input.enabled.set(False)
            logger.warning("Disabled ARC on 461 before piezo walk")

        target = self.target_offset.get()
        volts = pc.voltage_set.get()
        offset = self._read_offset()
        logger.info(
            "Start: piezo %.2f V, detuning %.3f GHz", volts, 1e-9 * offset
        )

        # Establish local slope with a 1 V probe step
        probe = 1.0 if volts < (VOLT_MIN + VOLT_MAX) / 2 else -1.0
        pc.voltage_set.set(volts + probe)
        time.sleep(3)
        new_offset = self._read_offset()
        slope = (new_offset - offset) / probe
        volts += probe
        offset = new_offset
        logger.info("Probe step: slope %.2f GHz/V", 1e-9 * slope)

        if not abs(slope) > 0.1e9:
            raise RuntimeError(
                f"Piezo slope too small to steer ({slope:.3g} Hz/V) - "
                "is the wand reading the 461?"
            )

        for step in range(MAX_STEPS):
            error = target - offset
            if abs(error) < self.handoff_range.get():
                break

            dv = max(-MAX_STEP_V, min(MAX_STEP_V, error / slope))
            new_volts = volts + dv
            if not VOLT_MIN < new_volts < VOLT_MAX:
                raise RuntimeError(
                    f"Refusing to walk piezo to {new_volts:.1f} V "
                    f"(detuning still {1e-9 * offset:.2f} GHz)"
                )

            pc.voltage_set.set(new_volts)
            time.sleep(3)
            new_offset = self._read_offset()

            moved = new_offset - offset
            if abs(dv) > 0.2:
                measured = moved / dv
                if abs(measured) > 0.1e9:
                    slope = 0.5 * slope + 0.5 * measured

            volts = new_volts
            offset = new_offset
            logger.info(
                "Step %d: piezo %.2f V, detuning %.3f GHz (slope %.2f GHz/V)",
                step,
                volts,
                1e-9 * offset,
                1e-9 * slope,
            )
        else:
            raise RuntimeError(
                f"Did not reach handoff range in {MAX_STEPS} steps "
                f"(detuning {1e-9 * offset:.2f} GHz)"
            )

        logger.info(
            "Within %.1f GHz - handing off to the WAND lock at %.1f MHz",
            1e-9 * self.handoff_range.get(),
            1e-6 * target,
        )
        self.wand_steering.steer_wand(
            "461",
            offset=target,
            timeout=180.0,
            required_accuracy=2e6,
            leave_locked=True,
        )


Steer461PiezoToWand = make_fragment_scan_exp(Steer461PiezoToWandFrag)
