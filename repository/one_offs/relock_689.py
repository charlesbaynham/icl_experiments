"""
Relock the Toptica 689nm ECDL to the cavity

This is a test script which will be incorporated into a QButler Calibration
later.

The plan based on manual fiddling is:

1. Set 689nm ECDL to:
    FALC enabled Unlim disabled Piezo scan disabled

2. Use WAND to steer it back to 0 MHz offset (don't mess with the setpoint -
   SwitchIsotope should have made sure we're set correctly for the current EOM
   sidebands)

3. Set piezo scan enabled (10 Hz, 0.05V)

4. Set Unlim enabled

5. Set scan disabled

6 Check transmission

7. If high, done. If low, repeat from 2.
"""
import time

from artiq.coredevice.core import Core
from artiq.experiment import now_mu
from ndscan.experiment import *
from ndscan.experiment import ExpFragment
from ndscan.experiment import Fragment
from ndscan.experiment import make_fragment_scan_exp
from ndscan.experiment.parameters import FloatParamHandle
from ndscan.experiment.parameters import IntParamHandle
from toptica_wrapper.driver import TopticaDLCPro
from wand.server import ControlInterface as WANDControlInterface

from repository.lib.fragments.blue_3d_mot import Blue3DMOTFrag
from repository.lib.fragments.cameras.dual_camera_measurer import DualCameraMeasurement
from repository.lib.fragments.set_eom_sidebands import SetEOMSidebandsFrag


class RelockCavity(Fragment):
    def build_fragment(self):
        self.setattr_param(
            "piezo_scan_amplitude", FloatParam, default=0.05, unit="V", min=0
        )
        self.piezo_scan_amplitude: FloatParamHandle

        self.setattr_param(
            "piezo_scan_frequency", FloatParam, default=10, unit="Hz", min=0
        )
        self.piezo_scan_frequency: FloatParamHandle

        self.setattr_param(
            "delay_before_unlim", FloatParam, default=0.1, unit="ms", min=0
        )
        self.delay_before_unlim: FloatParamHandle

        self.setattr_param(
            "delay_after_unlim", FloatParam, default=0.2, unit="ms", min=0
        )
        self.delay_after_unlim: FloatParamHandle

        self.setattr_param("max_attempts", IntParam, default=3, min=1)
        self.max_attempts: IntParamHandle

        self.setattr_device("wand_server")
        self.wand_server: WANDControlInterface

        self.setattr_device("toptica_689")
        self.toptica_689: TopticaDLCPro

    def relock(self):
        attempts = 0

        while not self.is_cavity_locked():
            attempts += 1
            if attempts >= self.max_attempts.get():
                raise RuntimeError("Max attempts reached and cavity is still unlocked")

            self.set_piezo_scan(enabled=False)
            self.set_FALC(main=False, unlim=False)

            self.wand_steer(laser="689", offset=0.0, timeout=20)

            self.set_piezo_scan(
                enabled=True,
                amplitude=self.piezo_scan_amplitude.get(),
                frequency=self.piezo_scan_frequency.get(),
            )
            self.set_FALC(main=True, unlim=False)

            time.sleep(self.delay_before_unlim.get())

            self.set_FALC(main=True, unlim=True)

            time.sleep(self.delay_after_unlim.get())

            self.set_piezo_scan(enabled=False)

    def set_piezo_scan(self, enabled=False, amplitude=0.0, frequency=1.0):
        self.toptica_689.get_laser().scan.enabled.set(False)
        self.toptica_689.get_laser().scan.amplitude.set(amplitude)
        self.toptica_689.get_laser().scan.frequency.set(frequency)
        self.toptica_689.get_laser().scan.enabled.set(enabled)

    def set_FALC(self, main=False, unlim=False):
        raise NotImplementedError
