from artiq.coredevice.core import Core
from artiq.language import delay
from artiq.language import kernel
from ndscan.experiment import Fragment
from ndscan.experiment.parameters import FloatParam
from ndscan.experiment.parameters import FloatParamHandle
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
            "sweep_time",
            FloatParam,
            description="Probe sweep duration",
            default=1e-3,
            min=1e-6,
            unit="ms",
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

        self.sweep_time: FloatParamHandle
        self.max_f: FloatParamHandle
        self.min_f: FloatParamHandle

    @kernel
    def trigger_single_sweep(self):
        """
        Trigger a single sweep of the pulse
        Also advances the timeline by the given sweep time.
        """

        df_dt = (self.max_f.get() - self.min_f.get()) / self.sweep_time.get()

        self.probe_ramper.start_ramp(
            df_dt,
            self.min_f.get(),
            self.max_f.get(),
        )
        # Wait until we do one pulse
        delay(self.sweep_time.get())
        self.probe_ramper.stop_ramp()
