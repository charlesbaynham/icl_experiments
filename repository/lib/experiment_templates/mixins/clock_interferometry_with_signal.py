import logging

import numpy as np
from artiq.coredevice.core import Core
from artiq.language import kernel
from artiq.language import now_mu
from ndscan.experiment.fragment import Fragment
from ndscan.experiment.parameters import FloatParam
from ndscan.experiment.parameters import FloatParamHandle
from pyaion.fragments.suservo import LibSetSUServoStatic

from repository.lib import constants
from repository.lib.experiment_templates.mixins.clock_interferometry import (
    ClockInterferometryBase,
)

logger = logging.getLogger(__name__)


class StarkShifterWithSignalMixin(ClockInterferometryBase):
    """
    Controls the setpoint of the Stark shifter to add a fake, sinusoidal signal
    to the differential phase shift

    Kernel hooks used (multiple mixins cannot use the same hooks):
        * set_shifter_setpoint_hook
    """

    def build_fragment(self):
        # %% Fragments

        # Create a subfragment so we can avoid polluting the main namespace +
        # have access to device_setup
        #
        # Do this before the super().build_fragment() call, so that this
        # fragment is executed first in the list of subfragments, allowing it to
        # pre-calculate values that the clock spectroscopy subfragment will use
        class SignalInjector(Fragment):

            def build_fragment(self, parent_fragment: "StarkShifterWithSignalMixin"):
                self.setattr_device("core")
                self.core: Core

                # Store a reference to the parent fragment
                self.parent_fragment = parent_fragment

                self.setattr_fragment(
                    "stark_shifter_suservo",
                    LibSetSUServoStatic,
                    constants.SUSERVOED_BEAMS[
                        "stark_shifter_689_delivery"
                    ].suservo_device,
                )
                self.stark_shifter_suservo: LibSetSUServoStatic

                self.t0_mu = np.int64(0)
                self.period_mu = np.int64(0)

            @kernel
            def device_setup(self):
                self.device_setup_subfragments()

                # ...on first run
                if self.t0_mu == 0:
                    # Initialise t0 based on the RTIO time when the experiment is started
                    self.t0_mu = self.core.get_rtio_counter_mu()

                # Calculate the period in machine units
                self.period_mu = self.core.seconds_to_mu(
                    1 / self.parent_fragment.stark_shifter_setpoint_frequency.get()
                )

                # Every run, set the Stark shifter setpoint to the value
                # relevant for the current time. We'll set it again closer to
                # the probes, but we want to let the setpoint stabilise
                self.core.break_realtime()
                self.set_stark_shifter_setpoint()

            @kernel
            def set_stark_shifter_setpoint(self, t_pulse_mu=np.int64(0)):
                """
                Set the Stark shifter setpoint based on the value of
                t_pulse, or now_mu() by default
                """
                amplitude = self.parent_fragment.stark_shifter_setpoint_amplitude.get()
                frequency = self.parent_fragment.stark_shifter_setpoint_frequency.get()
                mean = self.parent_fragment.stark_shifter_setpoint_mean.get()

                if t_pulse_mu == 0:
                    t_pulse_mu = now_mu()

                # Calculate t relative to the start of the current oscillation,
                # in integer mathematics, to avoid floating point errors for
                # long-running experiments
                t_mu = (t_pulse_mu - self.t0_mu) % self.period_mu
                t = self.core.mu_to_seconds(t_mu)

                new_setpoint = mean + amplitude * np.sin(2 * np.pi * frequency * t)

                self.stark_shifter_suservo.set_setpoint(new_setpoint)

        self.setattr_fragment("signal_injector", SignalInjector, self)
        self.signal_injector: SignalInjector

        super().build_fragment()

        # Override the Stark shifter's setpoint in the default setter: we'll do
        # this manually
        suservo_handles, _, _ = self.stark_shifter.set_defaults_delivery.get_handles()
        self.stark_shifter.set_defaults_delivery.override_param(
            param_name=suservo_handles[
                "stark_shifter_689_delivery"
            ].setpoint_handle.name,
            initial_value=None,
        )

        # Parameters for the signal
        self.setattr_param(
            "stark_shifter_setpoint_amplitude",
            FloatParam,
            "Amplitude of the Stark shifter sinusoid",
            default=constants.INTERFEROMETRY_SIGNAL_INJECTION_AMPLITUDE,
            unit="V",
        )
        self.stark_shifter_setpoint_amplitude: FloatParamHandle

        self.setattr_param(
            "stark_shifter_setpoint_frequency",
            FloatParam,
            "Frequency of the Stark shifter sinusoid",
            default=constants.INTERFEROMETRY_SIGNAL_INJECTION_FREQUENCY,
            unit="mHz",
        )
        self.stark_shifter_setpoint_frequency: FloatParamHandle

        self.setattr_param(
            "stark_shifter_setpoint_mean",
            FloatParam,
            "Mean of the Stark shifter sinusoid",
            default=constants.SUSERVOED_BEAMS["stark_shifter_689_delivery"].setpoint,
            unit="V",
        )
        self.stark_shifter_setpoint_mean: FloatParamHandle

    @kernel
    def after_clock_delivery_setup_hook(self, t_first_pulse_mu: np.int64):
        """
        Hook to set the Stark shifter setpoint

        Called after the clock delivery AOM is prepared, before the first
        spectroscopy pulse is fired.

        Use the subfragment to calculate a new stark shifter setpoint, based on
        the time that the pulse will be fired
        """

        self.signal_injector.set_stark_shifter_setpoint(t_pulse_mu=t_first_pulse_mu)
