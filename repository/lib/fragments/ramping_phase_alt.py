import logging
from typing import *

from artiq.coredevice.ad9910 import AD9910
from artiq.coredevice.core import Core
from artiq.coredevice.dma import CoreDMA
from artiq.experiment import at_mu
from artiq.experiment import delay_mu
from artiq.experiment import kernel
from artiq.experiment import now_mu
from artiq.experiment import portable
from artiq.experiment import TFloat
from ndscan.experiment import Fragment
from ndscan.experiment.parameters import FloatParam
from ndscan.experiment.parameters import FloatParamHandle
from numpy import int32
from numpy import int64
from pyaion.fragments.suservo import LibSetSUServoStatic


logger = logging.getLogger(__name__)


class GeneralRampingPhase(Fragment):
    """
    Template fragment for a phase of the experiment which allows:

        * Ramping of SUServo setpoints
        * Ramping of AD9910 detunings and amplitudes
        * General ramping of generic float parameters (e.g. for currents in a
          coil)

    This fragment should be subclassed for each desired phase. Default settings
    for its parameters can be set by setting the appropriate class variable.

    ### General ramping

    To ramp general parameters that aren't SUServos or AD9910s, you can define
    `general_setter_starts` and `general_setter_ends`. You must also pass a
    setter method to `build_fragment`, e.g.::

        # In your Fragment's build_fragment method
        self.setattr_fragment("ramping_phase", SubclassedGeneralRampingPhase,
        setters=my_setter.set)

    This method will be called once for each step of the ramp and passed a list
    of floats of the same size as `self.general_setter_starts`. You can use this
    to implement arbitary ramps, e.g. of currents in a coil.

    ### Good-to-knows

    Note that this phase does not support zero-length lists of any object type.
    This is because handling these is hard in ARTIQ, since empty lists do not
    have an associated type and so kernel compilation breaks. Working around
    this is possible, but not done yet. Better to wait for the new compiler
    which solves this problem.

    Lookup of pre-recorded sequences is slow, but can be done before the
    sequence runs. To do this, use :meth:`~.precalculate_dma_handle` before
    calling :meth:`~.do_phase`.
    """

    time_step_default = 100e-6

    duration_default: float = None

    urukuls: List[str] = []
    default_urukul_nominal_frequencies: List[float] = []
    default_urukul_detunings_start: List[float] = []
    default_urukul_detunings_end: List[float] = []
    default_urukul_amplitudes_start: List[float] = []
    default_urukul_amplitudes_end: List[float] = []

    suservos: List[str] = []
    default_suservo_nominal_setpoints: List[float] = []
    default_suservo_setpoint_multiples_start: List[float] = []
    default_suservo_setpoint_multiples_end: List[float] = []

    general_setter_names: List[str] = []
    general_setter_param_options: List[Dict] = []
    general_setter_default_starts: List[float] = []
    general_setter_default_ends: List[float] = []

    def validate_attributes(self, general_setter):
        assert self.duration_default is not None

        # validate the class attributes to make sure this class was declared correctly
        assert len(self.urukuls) == len(set(self.urukuls)), TypeError(
            "self.urukuls contains duplicate entries"
        )
        assert len(self.default_urukul_nominal_frequencies) == len(
            self.urukuls
        ), TypeError(
            "default_urukul_nominal_frequencies must have same length as self.urukuls"
        )
        assert len(self.default_urukul_detunings_start) == len(self.urukuls), TypeError(
            "default_urukul_detunings_start must have same length as self.urukuls"
        )
        assert len(self.default_urukul_detunings_end) == len(self.urukuls), TypeError(
            "default_urukul_detunings_end must have same length as self.urukuls"
        )

        assert len(self.default_urukul_amplitudes_start) == len(
            self.urukuls
        ), TypeError(
            "default_urukul_amplitudes_start must have same length as self.urukuls"
        )
        assert len(self.default_urukul_amplitudes_end) == len(self.urukuls), TypeError(
            "default_urukul_amplitudes_end must have same length as self.urukuls"
        )

        assert len(self.suservos) == len(set(self.suservos)), TypeError(
            "self.suservos_for_intensity contains duplicate entries"
        )
        assert len(self.default_suservo_setpoint_multiples_start) == len(
            self.suservos
        ), TypeError(
            "self.default_syservo_setpoints_start must have same length as self.suservos_for_intensity"
        )
        assert len(self.default_suservo_setpoint_multiples_end) == len(
            self.suservos
        ), TypeError(
            "self.default_syservo_setpoints_end must have same length as self.suservos_for_intensity"
        )

        assert len(self.general_setter_default_starts) == len(
            self.general_setter_default_ends
        ), TypeError(
            "self.general_setters_start must have same length as self.general_setters_end"
        )
        assert len(self.general_setter_names) == len(
            self.general_setter_default_ends
        ), TypeError(
            "self.general_setter_names must have same length as self.general_setters_end"
        )

        if len(self.general_setter_param_options) == 0:
            self.general_setter_param_options = [
                {} for _ in range(len(self.general_setter_default_starts))
            ]

        assert len(self.general_setter_param_options) == len(
            self.general_setter_default_ends
        ), TypeError(
            "self.general_setter_param_options must have same length as self.general_setters_end"
        )

        if len(self.general_setter_default_starts) > 0:
            assert general_setter is not None, TypeError(
                "If you define a general setter ramp, you must pass a general setter to `build_fragment`"
            )

    def build_fragment(self, *args, general_setter: Optional[Callable] = None):
        self.validate_attributes(general_setter)

        # %% Devices

        self.setattr_device("core")
        self.core: Core

        self.setattr_device("core_dma")
        self.core_dma: CoreDMA

        # Build ndscan parameters for all the ramping variables and arrays of
        # setters for the kernel to use
        self.suservo_setters_and_param_handles = self.build_suservos()
        self.ad9910_channels_and_param_handles = self.build_ad9910s()
        (
            self.general_setter,
            self.general_setter_param_handles,
        ) = self.build_general_setter(general_setter)

        # %% Other parameters

        self.setattr_param(
            "duration",
            FloatParam,
            "Duration of phase",
            default=self.duration_default,
            min=0.0,
            unit="ms",
        )
        self.setattr_param(
            "time_step",
            FloatParam,
            "Gap between steps",
            default=self.time_step_default,
            min=0.0,
            unit="us",
        )

        self.duration: FloatParamHandle
        self.time_step: FloatParamHandle

        # %% Kernel variables
        self.debug_enabled = logger.isEnabledFor(logging.DEBUG)
        self.dma_handle = (int32(0), int64(0), int32(0), False)
        self.dma_handle_valid = False

        # %% Kernel invariants
        kernel_invariants = getattr(self, "kernel_invariants", set())
        self.kernel_invariants = kernel_invariants | {
            "debug_enabled",
        }

    @kernel
    def do_nothing(self, num: TFloat):
        pass

    def build_general_setter(self, general_setter):
        setter_was_passed = len(self.general_setter_default_starts) == 0

        general_setter_param_handles: List[
            Tuple[
                FloatParamHandle,
                FloatParamHandle,
            ]
        ] = []

        if setter_was_passed:
            for name, options, start, end in zip(
                self.general_setter_names,
                self.general_setter_param_options,
                self.general_setter_default_starts,
                self.general_setter_default_ends,
            ):
                # For each passed parameter to the general setter, make an NDScan parameter
                start_handle = self.setattr_param(
                    f"{name}_start",
                    FloatParam,
                    f"Start value for {name}",
                    default=start,
                    **options,
                )

                end_handle = self.setattr_param(
                    f"{name}_end",
                    FloatParam,
                    f"End value for {name}",
                    default=end,
                    **options,
                )

                general_setter_param_handles.append((start_handle, end_handle))

        else:
            # ARTIQ doesn't like empty lists because it doesn't know what type they are.
            # Rather than work around this, I'll just make a general setter that does nothing.
            # This costs us 8ns per step of wasted time.
            general_setter = self.do_nothing

            # I also need to loop over parameter handles, so I must make a dummy
            # parameter to pass. I'll override it so that it doesn't appear in
            # the parameter listing
            dummy_handle = self.setattr_param(
                "dummy_param", FloatParam, "Dummy parameter - ignore me", default=0.0
            )
            self.override_param("dummy_param", 0.0)

            general_setter_param_handles.append((dummy_handle, dummy_handle))

        return general_setter, general_setter_param_handles

    def build_suservos(self):
        suservo_setters_and_param_handles: List[
            Tuple[
                LibSetSUServoStatic,
                FloatParamHandle,
                FloatParamHandle,
                FloatParamHandle,
            ]
        ] = []

        for suservo_name, setpoint_nominal, setpoint_start, setpoint_end in zip(
            self.suservos,
            self.default_suservo_nominal_setpoints,
            self.default_suservo_setpoint_multiples_start,
            self.default_suservo_setpoint_multiples_end,
        ):
            # For each requested SUServo, get a setter Fragment for it and
            # define parameters for the nominal setpoint, and the multiples of
            # that nominal value that this ramping phase should start and end
            # with. These will take default values defined by the class
            # attributes when a concrete instance of this class is created, but
            # the user will be able to override those value through normal
            # NDScan behaviour.
            setter = self.setattr_fragment(
                f"setter_{suservo_name}", LibSetSUServoStatic, suservo_name
            )

            setpoint_nominal_handle = self.setattr_param(
                f"setpoint_nominal_{suservo_name}",
                FloatParam,
                f"Nominal setpoint for {suservo_name}",
                min=0,
                unit="V",
                default=setpoint_nominal,
            )

            setpoint_start_handle = self.setattr_param(
                f"setpoint_multiple_start_{suservo_name}",
                FloatParam,
                f"Multiple of nominal setpoint at start of ramp for {suservo_name}",
                min=0,
                unit="V",
                default=setpoint_start,
            )

            setpoint_end_handle = self.setattr_param(
                f"setpoint_multiple_end_{suservo_name}",
                FloatParam,
                f"Multiple of nominal setpoint at end of ramp for {suservo_name}",
                min=0,
                unit="V",
                default=setpoint_end,
            )

            suservo_setters_and_param_handles.append(
                (
                    setter,
                    setpoint_nominal_handle,
                    setpoint_start_handle,
                    setpoint_end_handle,
                )
            )

        return suservo_setters_and_param_handles

    def build_ad9910s(self):
        ad9910_channels_and_param_handles: List[
            Tuple[
                AD9910,
                FloatParamHandle,
                FloatParamHandle,
                FloatParamHandle,
                FloatParamHandle,
                FloatParamHandle,
            ]
        ] = []

        for (
            urukul_channel_name,
            frequency_nominal,
            detuning_start,
            detuning_end,
            amplitude_start,
            amplitude_end,
        ) in zip(
            self.urukuls,
            self.default_urukul_nominal_frequencies,
            self.default_urukul_detunings_start,
            self.default_urukul_detunings_end,
            self.default_urukul_amplitudes_start,
            self.default_urukul_amplitudes_start,
        ):
            # For each requested SUServo, get a setter Fragment for it and
            # define parameters for the nominal setpoint, and the multiples of
            # that nominal value that this ramping phase should start and end
            # with. These will take default values defined by the class
            # attributes when a concrete instance of this class is created, but
            # the user will be able to override those value through normal
            # NDScan behaviour.
            channel: AD9910 = self.get_device(urukul_channel_name)

            nominal_freq_handle = self.setattr_param(
                f"frequency_nominal_{urukul_channel_name}",
                FloatParam,
                f"Nominal frequency for {urukul_channel_name}",
                min=0,
                unit="MHz",
                default=frequency_nominal,
            )

            detuning_start_handle = self.setattr_param(
                f"detuning_start_{urukul_channel_name}",
                FloatParam,
                f"Detuning from nominal frequency at start of ramp for {urukul_channel_name}",
                unit="MHz",
                default=detuning_start,
            )

            detuning_end_handle = self.setattr_param(
                f"detuning_end_{urukul_channel_name}",
                FloatParam,
                f"Detuning from nominal frequency at end of ramp for {urukul_channel_name}",
                unit="MHz",
                default=detuning_end,
            )

            amplitude_start_handle = self.setattr_param(
                f"amplitude_start_{urukul_channel_name}",
                FloatParam,
                f"Amplitude at start of ramp for {urukul_channel_name}",
                min=0,
                default=amplitude_start,
            )

            amplitude_end_handle = self.setattr_param(
                f"amplitude_end_{urukul_channel_name}",
                FloatParam,
                f"Amplitude at end of ramp for {urukul_channel_name}",
                min=0,
                default=amplitude_end,
            )

            amplitude_start

            ad9910_channels_and_param_handles.append(
                (
                    channel,
                    nominal_freq_handle,
                    detuning_start_handle,
                    detuning_end_handle,
                    amplitude_start_handle,
                    amplitude_end_handle,
                )
            )

        return ad9910_channels_and_param_handles

    @portable
    def _calc_step_size(self, start: TFloat, end: TFloat, num: TFloat) -> TFloat:
        return (end - start) / float(num - 1)

    @kernel
    def device_setup(self):
        """
        Records the ramps to DMA.
        Write events are staggered by 8 ns (self.core.ref_multiplier) to use
        only one lane
        """
        self.device_setup_subfragments()

        # Compute grid for writes
        num_points = 1 + int(self.duration.get() // self.time_step.get())
        time_step_mu = self.core.seconds_to_mu(self.duration.get() / float(num_points))

        # Compute step sizes and initial values for the general ramp
        general_values = [0.0] * len(self.general_setter_param_handles)
        general_steps = [0.0] * len(self.general_setter_param_handles)

        for i in range(len(self.general_setter_param_handles)):
            start_handle = self.general_setter_param_handles[i][0]
            end_handle = self.general_setter_param_handles[i][1]

            general_values[i] = start_handle.get()
            general_steps[i] = self._calc_step_size(
                start_handle.get(), end_handle.get(), num_points
            )

        suservo_values = [0.0] * len(self.suservo_setters_and_param_handles)
        suservo_steps = [0.0] * len(self.suservo_setters_and_param_handles)

        for i in range(len(self.suservo_setters_and_param_handles)):
            nom_setpoint_handle = self.suservo_setters_and_param_handles[i][1]
            start_multiple_handle = self.suservo_setters_and_param_handles[i][2]
            end_multiple_handle = self.suservo_setters_and_param_handles[i][3]

            # Get the start point for all the SUServo intensities
            suservo_values[i] = nom_setpoint_handle.get()

            # Calculate the step sizes for all the SUServo steps
            suservo_steps[i] = self._calc_step_size(
                suservo_values[i] * start_multiple_handle.get(),
                suservo_values[i] * end_multiple_handle.get(),
                num_points,
            )

        frequency_values = [0.0] * len(self.ad9910_channels_and_param_handles)
        frequency_steps = [0.0] * len(self.ad9910_channels_and_param_handles)
        amplitude_steps = [0.0] * len(self.ad9910_channels_and_param_handles)
        amplitude_values = [0.0] * len(self.ad9910_channels_and_param_handles)

        for i in range(len(self.ad9910_channels_and_param_handles)):
            nominal_freq_handle = self.ad9910_channels_and_param_handles[i][1]
            detuning_start_handle = self.ad9910_channels_and_param_handles[i][2]
            detuning_end_handle = self.ad9910_channels_and_param_handles[i][3]
            amplitude_start_handle = self.ad9910_channels_and_param_handles[i][4]
            amplitude_end_handle = self.ad9910_channels_and_param_handles[i][5]

            # Get the start point for all the AD9910 parameters
            frequency_values[i] = (
                nominal_freq_handle.get() + detuning_start_handle.get()
            )
            amplitude_values[i] = amplitude_start_handle.get()

            # Calculate the step sizes for all the AD9910 channels
            frequency_steps[i] = self._calc_step_size(
                detuning_start_handle.get(), detuning_end_handle.get(), num_points
            )
            amplitude_steps[i] = self._calc_step_size(
                amplitude_start_handle.get(), amplitude_end_handle.get(), num_points
            )

        # Record these ramping parameters into a DMA sequence
        with self.core_dma.record(self.fqn):
            t_this_cycle_mu = now_mu()
            t_one_cycle_mu = int64(self.core.ref_multiplier)

            # Play the ramp
            for i_step in range(num_points):
                if self.debug_enabled:
                    logger.info("Saving trace %d of %d", i_step, num_points)

                at_mu(t_this_cycle_mu)

                # FIXME: General setting goes first since it often writes into the past (e.g. for Zotinos)
                # self.gradient_current_setter.set_currents([this_current])

                # delay_mu(t_one_cycle_mu)  # Avoid using multiple lanes

                # Set AD9910 frequencies
                for i in range(len(self.ad9910_channels_and_param_handles)):
                    ad9910 = self.ad9910_channels_and_param_handles[i][0]

                    if self.debug_enabled:
                        logger.info(
                            "Setting AD9910 %s to %.6f, amplitude=%f",
                            ad9910,
                            frequency_values[i],
                            amplitude_values[i],
                        )

                    ad9910.set(
                        frequency=frequency_values[i], amplitude=amplitude_values[i]
                    )
                    delay_mu(t_one_cycle_mu)  # Avoid using multiple lanes

                    frequency_values[i] += frequency_steps[i]
                    amplitude_values[i] += amplitude_steps[i]

                # Set suservo setpoints
                for i in range(len(self.suservo_setters_and_param_handles)):
                    suservo_channel = self.suservo_setters_and_param_handles[i][0]
                    suservo_channel.set_setpoint(suservo_values[i])
                    suservo_values[i] += suservo_steps[i]

                    delay_mu(t_one_cycle_mu)

                t_this_cycle_mu += time_step_mu

        if self.debug_enabled:
            logger.info('Saving dma trace as "%s"', self.fqn)

    @kernel
    def precalculate_dma_handle(self):
        self.dma_handle = self.core_dma.get_handle(self.fqn)
        self.dma_handle_valid = True

    @kernel
    def do_phase(self):
        """
        Perform the ramps (or steps) associated with this phase, as configured
        by the parameters

        Advances the timeline to the end of the ramp
        """

        t_end_mu = now_mu() + self.core.seconds_to_mu(self.duration.get())

        # It's nicer to use handles here instead of string lookup.
        # Unfortunately, the DMA handle changes whenever another DMA sequence is
        # recorded, so this Fragment can't handle the case that another Fragment
        # uses DMA after this Fragment's device_setup completes. If the user
        # needs the performance of pre-pre-computed handles, they should call
        # precalculate_dma_handle before this method.
        if self.dma_handle_valid:
            self.core_dma.playback_handle(self.dma_handle)
        else:
            self.core_dma.playback(self.fqn)

        # Ensure that the timeline points to the end of the phase, not just the
        # final RTIO point
        at_mu(t_end_mu)
