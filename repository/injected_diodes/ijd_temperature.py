import logging
from typing import Optional

from artiq.coredevice.core import Core
from artiq.experiment import EnumerationValue
from artiq.master.scheduler import Scheduler
from koheron_ctl200_laser_driver import CTL200
from ndscan.experiment.entry_point import make_fragment_scan_exp
from ndscan.experiment.fragment import ExpFragment
from ndscan.experiment.parameters import BoolParam
from ndscan.experiment.parameters import BoolParamHandle
from ndscan.experiment.parameters import FloatParam
from ndscan.experiment.parameters import FloatParamHandle
from ndscan.experiment.result_channels import FloatChannel

import repository.lib.constants as constants
from repository.lib.constants import IJD_DEFAULTS

# from ndscan.experiment import Fragment

logger = logging.getLogger(__name__)


class IJDTempFrag(ExpFragment):
    """
    IJD Temperature Control Fragment
    """

    def build_fragment(
        self,
        controller_name: Optional[str] = None,
        *args,
        **kwargs,
    ) -> None:
        if controller_name:
            defaults = IJD_DEFAULTS[controller_name]
        else:
            defaults = constants.IJD_DEFAULTS["blue_IJD1_controller"]

        if controller_name is not None:
            logger.debug("Controller name provided - hard coding")
            self.controller_name = controller_name
        else:
            logger.debug("Controller name not provided - setting up as an argument")
            # Choose the controller to set:
            controller_names = [
                k
                for k, v in self.get_device_db().items()
                if (
                    # Our unit tests replace controllers with local Mock
                    # objects, but also add a field called "mocked" with value
                    # True
                    ("type" in v and (v["type"] == "controller" or "mocked" in v))
                    and (
                        "command" in v
                        and "aqctl_koheron_ctl200_laser_driver" in v["command"]
                    )
                )
            ]
            if not controller_names:
                raise ValueError("No CTL200 Koheron controllers found in device_db")
            self.setattr_argument(
                "controller_name",
                EnumerationValue(controller_names, default=controller_names[0]),
            )

        # Get the passed controller's associated beat detection channel
        if self.controller_name is not None:  # i.e. not in build() for the GUI
            self.ijd_controller: CTL200 = self.get_device(self.controller_name)

        self.setattr_param(
            "set_gains",
            BoolParam,
            description="Set the IJD controller gains?",
            default=False,
        )
        self.set_gains: BoolParamHandle

        self.override_param("set_gains", False)

        self.setattr_param(
            "p_gain",
            FloatParam,
            description="P gain for the IJD controller",
            default=defaults.p_gain,
            min=0.0,
            max=0.09,
            step=0.0001,
        )
        self.p_gain: FloatParamHandle

        self.setattr_param(
            "i_gain",
            FloatParam,
            description="I gain for the IJD controller",
            default=defaults.i_gain,
            min=0.0,
            max=0.09,
            step=0.000001,
        )
        self.i_gain: FloatParamHandle

        self.setattr_param(
            "d_gain",
            FloatParam,
            description="D gain for the IJD controller",
            default=defaults.d_gain,
            min=0.0,
            max=0.09,
            step=0.000001,
        )
        self.d_gain: FloatParamHandle

        # for k, v in IJD_RELOCKER_DEFAULTS.items():
        #     if v.associated_controller == controller_name:
        #         self.relocker_frag: RelockerChannelFrag = self.setattr_fragment(
        #             f"frag_{k}", RelockerChannelFrag, k
        #         )

        # # Disable AOM setting by the scanner - we'll handle it here
        # self.frag_ijd_scanner.override_param("change_aom", False)

        # self.setattr_device("influx_logger")
        # self.influx_logger: InfluxController

        self.setattr_device("scheduler")
        self.scheduler: Scheduler

        self.setattr_device("core")
        self.core: Core

        self.controller_name = controller_name

        self.temperature_read: FloatChannel = self.setattr_result(
            f"T_read_{controller_name}", FloatChannel, display_hints={"priority": -1}
        )

        self.temperature_error: FloatChannel = self.setattr_result(
            f"T_err_{controller_name}", FloatChannel
        )

    def host_setup(self):
        super().host_setup()
        logger.info(
            f"Current IJD controller gains: P={self.get_p_gain()}, I={self.get_i_gain()}, D={self.get_d_gain()}"
        )

        # Request the ijd controller device

        # self.auto_relocking = self.relocker_frag.get_auto_relock()
        # self.relocker_frag.set_auto_relock(False)

    def run_once(self) -> None:

        if self.set_gains.get():
            logger.info(
                f"Setting IJD controller gains: P={self.p_gain.get()}, I={self.i_gain.get()}, D={self.d_gain.get()}"
            )

            self.set_p_gain(self.p_gain.get())
            self.set_i_gain(self.i_gain.get())
            self.set_d_gain(self.d_gain.get())

        setpoint = self.ijd_controller.get_temperature_setpoint()
        actual = self.ijd_controller.get_temperature_actual()
        error = setpoint - actual

        self.temperature_read.push(actual)
        self.temperature_error.push(error)

    def host_cleanup(self):
        # self.relocker_frag.set_auto_relock(self.auto_relocking)
        super().host_cleanup()

    def get_p_gain(self) -> float:
        """
        Read the P gain from the IJD controller.
        """
        return self.ijd_controller.get_p_gain()

    def set_p_gain(self, p_gain: float) -> None:
        """
        Set the P gain on the IJD controller.
        """
        self.ijd_controller.set_p_gain(p_gain)

    def set_i_gain(self, i_gain: float) -> None:
        """
        Set the I gain on the IJD controller.
        """
        self.ijd_controller.set_i_gain(i_gain)

    def get_i_gain(self) -> float:
        """
        Read the I gain from the IJD controller.
        """
        return self.ijd_controller.get_i_gain()

    def set_d_gain(self, d_gain: float) -> None:
        """
        Set the D gain on the IJD controller.
        """
        self.ijd_controller.set_d_gain(d_gain)

    def get_d_gain(self) -> float:
        """
        Read the D gain from the IJD controller.
        """
        return self.ijd_controller.get_d_gain()


class AllIJDTempFrag(ExpFragment):
    """
    Fragment to run all IJD temperature control fragments.
    """

    def build_fragment(self, *args, **kwargs) -> None:

        # self.setattr_param(
        #     "set_gains", BoolParam, description="Write gains", default=False
        # )
        # self.set_gains: BoolParamHandle

        self.ijd_temp_frags: list[IJDTempFrag] = []
        for controller_name in IJD_DEFAULTS.keys():
            # Create a fragment for each IJD controller
            frag = self.setattr_fragment(
                f"ijd_temp_frag_{controller_name}",
                IJDTempFrag,
                controller_name=controller_name,
            )
            self.ijd_temp_frags.append(frag)
            # frag.bind_param("set_gains", self.set_gains)

    def run_once(self) -> None:
        """
        Run all IJD temperature control fragments.
        """
        for frag in self.ijd_temp_frags:
            frag.run_once()


AllIJDTemp = make_fragment_scan_exp(AllIJDTempFrag)
