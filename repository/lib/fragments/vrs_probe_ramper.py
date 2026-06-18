from artiq.coredevice.core import Core
from artiq.language import kernel
from ndscan.experiment import Fragment
from ndscan.experiment.parameters import FloatParam
from ndscan.experiment.parameters import FloatParamHandle
from numpy import ceil
from numpy import int32
from pyaion.fragments.ad9910_ramper import AD9910Ramper


class VRS_Probe_Ramper(Fragment):
    """
    This fragment controls the DDS that generates RF ramp that shifts the frequency
    of the 689 AM to probe the VRS in the squeezing setup
    """

    def build_fragment(self, ad9910_name=None):
        self.setattr_device("core")
        self.core: Core

        self.setattr_fragment("probe_ramper", AD9910Ramper, ad9910_name)
        self.probe_ramper: AD9910Ramper

        self.setattr_param(
            "dF_dt",
            FloatParam,
            description="Rate of change of frequency",
            default=20e3,
            min=1,
            unit="kHz",
        )

        self.setattr_param(
            "max_f",
            FloatParam,
            description="Final scan frequency",
            default=50e6,
            min=1,
            unit="MHz",
        )

        self.setattr_param(
            "min_f",
            FloatParam,
            description="Initial scan frequency",
            default=0.0,
            unit="MHz",
        )

        # set the maximum frequency, this needs to be larger than the VRS as we
        # plan on overshooting this value.

        self.dF_dt: FloatParamHandle
        self.max_f: FloatParamHandle
        self.min_f: FloatParamHandle

    @kernel
    def device_setup(self) -> None:
        self.core.break_realtime()

        self.device_setup_subfragments()

        self.core.break_realtime()

        # Now we want to set the parameters of the AD9910 Ramper manually
        self.probe_ramper.set_ramp_limits(
            frequency_low=self.min_f.get(), frequency_high=self.max_f.get()
        )

        # As defined in the Datasheet this is the smallest value of M possible, i.e. with P = 1
        M_factor = (
            (4.0 * (2.0**32.0)) * self.dF_dt.get() / self.probe_ramper.dds.sysclk**2.0
        )

        # Don't allow steps smaller than 1000 LSBs otherwise we'll be very coarse in our frequency setting
        freq_step_mu = int32(max(ceil(M_factor), 1000.0))
        delay_mu = int32(round(freq_step_mu / M_factor))

        self.probe_ramper.set_ramp_parameters_mu(
            pos_freq_step_mu=freq_step_mu,
            pos_delay_mu=delay_mu,
            neg_freq_step_mu=freq_step_mu,
            neg_delay_mu=delay_mu,
        )

        # The main difference compared with the pyaion is that the probe ramper has the no-dwell modes on low
        # and is not triggered
        self.probe_ramper._extended_set_cfr2(
            drg_enable=1, no_dwell_low=0, no_dwell_high=0
        )

    @kernel
    def trigger(self):
        """
        Trigger the ramp
        """
        self.probe_ramper._pulse_io_update()

    @kernel
    def stop(self):
        """
        Stop the ramp
        """
        self.probe_ramper.stop_ramp()
