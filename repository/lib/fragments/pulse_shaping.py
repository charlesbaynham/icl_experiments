import abc
import logging

import artiq.coredevice.ad9910 as ad9910
import artiq.coredevice.urukul as urukul
import numpy as np
from artiq.coredevice.ad9910 import AD9910
from artiq.coredevice.core import Core
from artiq.coredevice.urukul import CFG_RST
from artiq.coredevice.urukul import CPLD
from artiq.language import TInt32
from artiq.language import TList
from artiq.language import delay
from artiq.language import kernel
from artiq.language import portable
from artiq.language import rpc
from ndscan.experiment import Fragment
from ndscan.experiment.parameters import FloatParam
from ndscan.experiment.parameters import FloatParamHandle
from ndscan.experiment.parameters import IntParam
from ndscan.experiment.parameters import IntParamHandle
from numpy import int64
from pyaion.fragments.urukul_init import make_urukul_init

logger = logging.getLogger(__name__)

# Use the default profile for RAM mode. See lab book entry 2025-04-07 for reasoning
RAM_PROFILE = urukul.DEFAULT_PROFILE


class _ShapedPulse(Fragment, abc.ABC):
    """
    Use an AD9910 channel to generate a shaped pulse

    To use this fragment you must subclass it and implement two methods,
    describing the pulse shape you want:

    1. `generate_amplitudes_and_phases`: This function must return a tuple of
       numpy arrays specifying the amplitude and phase of the pulse shape. This will probably be an RPC, though that's up to you.

    2. `is_recalc_needed`: This function must return True if the pulse shape
       needs to be recalculated, and False if it doesn't. This allows the
       Fragment to avoid recalculating / rewriting DDS RAM between scan shots if
       it's not needed. This ideally should be a kernel method, for speed.

    See :class:`~.BlackmanShapedPulse` for an example.
    """

    ad9910_name: str = None

    ram_modulation_mode = None
    "The type of RAM modulation to be applied. Frequency, amplitude, phase, or phase+amplitude (phasor)"

    ram_ramp_mode = ad9910.RAM_MODE_RAMPUP
    "RAM playback mode - see AD9910 datasheet for details. Default to a repeating ramp upwards through RAM addresses"

    ram_nodwell_mode = 0
    "NODWELL mode. 0 means wait at the top of the ramp through RAM, 1 means loop back"

    def __init__(self, *args, **kwargs):
        if self.ram_modulation_mode is None:
            raise ValueError("ram_modulation_mode must be set in subclass")

        super().__init__(*args, **kwargs)

    @abc.abstractmethod
    def is_recalc_needed(self) -> bool:
        """
        This function must be defined by the user to determine if the pulse
        shape needs to be recalculated. It should return True if it does, and
        False if it doesn't.

        Implementing this saves a lot of network traffic, and therefore time.
        Ideally this should be a @kernel method, but an RPC is OK too, just a
        bit slower.
        """

    def build_fragment(self, ad9910_name=None):
        self.setattr_device("core")
        self.core: Core

        if ad9910_name is None and self.ad9910_name is None:
            raise ValueError("No AD9910 name provided")
        elif ad9910_name is not None:
            self.ad9910_name = ad9910_name

        # Make sure the Urukul is initialized
        self.setattr_fragment("urukul_init", make_urukul_init([self.ad9910_name]))

        self.dds: AD9910 = self.get_device(self.ad9910_name)

        self._min_duration_of_one_step = 4.0 / 1e9
        self._max_duration_of_one_step = self._min_duration_of_one_step * 2**16
        self._max_num_steps = 1024

        self.setattr_param(
            "num_steps",
            IntParam,
            description="Number of steps in the shaped pulse",
            default=1024,
            min=1,
            max=self._max_num_steps,
        )
        self.num_steps: IntParamHandle

        self.setattr_param(
            "pulse_duration",
            FloatParam,
            description="Duration of the pulse",
            unit="us",
            default=100e-6,
            min=self._min_duration_of_one_step,
            max=self._max_duration_of_one_step * self._max_num_steps,
        )
        self.pulse_duration: FloatParamHandle

    @portable
    def _seconds_to_ram_mu(self, seconds: float):
        """
        Convert a time in seconds to the number of RAM step LSBs.
        """
        return int(round(seconds / (4.0 / self.dds.sysclk)))

    def host_setup(self):
        super().host_setup()

        # Done in host_setup so that dds.cpld exists:
        self.cpld: CPLD = self.dds.cpld

        # for replacement in kernel
        self._step_mu = 0
        self._step_duration = 0.0

    @abc.abstractmethod
    def _get_ram_words(self) -> TList(TInt32):
        """
        Subclasses must implement this method as a synchronous RPC. It must
        return a list of int32s, n_words long, that will be written into RAM.
        """

    @abc.abstractmethod
    def prepare_pulse(self):
        pass

    @kernel
    def device_setup(self):
        self.device_setup_subfragments()

        if (
            self.pulse_duration.get()
            > self.num_steps.get() * self._max_duration_of_one_step
        ):
            logger.error(
                "Pulse duration %.3f ms is too long for %d steps",
                self.pulse_duration.get() * 1e3,
                self.num_steps.get(),
            )
            raise ValueError("Pulse duration is too long")

        self._step_duration = self.pulse_duration.get() / self.num_steps.get()

        self._step_mu = min(
            self._seconds_to_ram_mu(self._step_duration),
            0xFFFF,
        )

        if self.is_recalc_needed():
            self._store_waveform_in_ram()

    @kernel
    def _store_waveform_in_ram(self):
        ram_data = self._get_ram_words()
        self._write_ram(ram_data)

        # Check that the data was written correctly. This takes ~4ms so could be
        # removed if we wanted to speed things up
        self._check_ram_data(ram_data)

    @kernel
    def _check_ram_data(self, desired_ram_data):
        read_data = [np.int32(0x00)] * len(desired_ram_data)
        self.core.break_realtime()
        self._read_ram(read_data)

        error = False
        for i in range(len(desired_ram_data)):
            if desired_ram_data[i] != read_data[i]:
                error = True
                logger.error(
                    "RAM data mismatch at index %d: expected %s, got %s",
                    i,
                    desired_ram_data[i],
                    read_data[i],
                )

        if error:
            logger.error("RAM data mismatch, aborting")
            self._urukul_rst(self.cpld)

            raise RuntimeError("RAM data mismatch")

    @kernel
    def _read_ram(self, read_data):
        self.dds.set_profile_ram(
            start=0x00,
            end=len(read_data) - 1,
            profile=RAM_PROFILE,
        )
        self.cpld.io_update.pulse_mu(8)  # assumes 8 mu > t_SYN_CCLK
        assert RAM_PROFILE == urukul.DEFAULT_PROFILE

        self.dds.read_ram(read_data)

    @kernel
    def _enter_RAM_mode(self):
        """
        Prepare for playback of the sequence recorded in RAM

        This will enable RAM mode for this DDS - you cannot use it as a normal
        DDS until you call `disable_ram_mode`.

        You should call `trigger_pulse` after this to actually play the
        sequence, and call `disable_ram_mode` afterwards to clean up.
        """
        # Disable RAM mode while changing profile
        self.dds.set_cfr1(ram_enable=0, ram_destination=self.ram_modulation_mode)
        self.cpld.io_update.pulse_mu(8)  # assumes 8 mu > t_SYN_CCLK

        self.dds.set_profile_ram(
            start=0x00,
            end=self.num_steps.get() - 1,
            step=self._step_mu,
            mode=self.ram_ramp_mode,
            profile=RAM_PROFILE,
            nodwell_high=self.ram_nodwell_mode,
        )

        # This is a no-op since we are already on the right profile unless the
        # user has taken control themselves. So it's commented out with a check
        assert RAM_PROFILE == urukul.DEFAULT_PROFILE

        # Enable RAM mode - the next IO_UPDATE will start playback
        self.dds.set_cfr1(ram_enable=1, ram_destination=self.ram_modulation_mode)

    @kernel
    def start_output(self):
        """
        Start playback of the configured shape. This should be called after
        `prepare_playback`.

        This will turn on the RF switch and trigger the RAM playback. Whether it
        loops forever or only fires only once depends on the choice of NODWELL mode.
        """
        self.dds.sw.on()
        self.cpld.io_update.pulse_mu(int64(self.core.ref_multiplier))

    @kernel
    def trigger_pulse(self):
        """
        Fire the configured pulse. This should be called after `prepare_playback`.

        Advances the timeline by the duration of the pulse
        """
        self.start_output()
        delay(self._step_duration * self.num_steps.get())
        self.stop_output()

    @kernel
    def stop_output(self):
        """
        Stop playback of the configured shape. This should be called after `start_output`.
        """
        self.dds.sw.off()

    @kernel
    def disable_ram_mode(self):
        """
        Disable RAM mode and return the DDS to its default state.

        This will:

        * Disable RAM mode
        * Set the PROFILE back to the default
        """
        self.dds.set_cfr1(ram_enable=0)

        # This is a no-op since we are already on the right profile unless the
        # user has taken control themselves. So it's commented out with a check
        # self.cpld.set_profile(RAM_PROFILE)
        assert RAM_PROFILE == urukul.DEFAULT_PROFILE

        self.cpld.io_update.pulse_mu(8)  # assumes 8 mu > t_SYN_CCLK

    @kernel
    def _write_ram(
        self,
        data: list[np.int32],
        break_realtime: bool = True,
        offset=0,
        chunk_size=256,
    ):
        """
        Write a list of 32-bit integers into the AD9910's RAM

        To do this, this function will alter the PROFILE pins for all four
        AD9910s on this Urukul, but put them back afterwards to ARTIQ's default
        setting.

        The data will be stored starting at address <offset> and must be a
        maximum of 1024 words long.

        Interpretation is left to the user to define elsewhere.

        Args:
            data (list[np.int32]): List of 32-bit data words to store.
        """

        # Check that the data is the right length
        if offset + len(data) > 1024:
            raise ValueError("Data length + offset exceeds 1024 words")

        # To work around annoying-ARTIQ-bug
        # https://github.com/m-labs/artiq/issues/1378, write in chunks. Note the
        # organisation of the AD9910's RAM. This is confusing! But was
        # discovered by trial and error. See obsidian notes from 2025-04-09.
        if len(data) > chunk_size:
            N = len(data)
            self._write_ram(
                data[N - chunk_size :],
                break_realtime=break_realtime,
                offset=offset,
                chunk_size=chunk_size,
            )
            self._write_ram(
                data[: N - chunk_size],
                break_realtime=break_realtime,
                offset=offset + chunk_size,
                chunk_size=chunk_size,
            )

        else:
            if break_realtime:
                duration_of_write = len(data) * 32 * (1 / 125e6)  # 32 bits at 125 MHz
                # Allow 5x this for safety, since underflows here will corrupt the
                # AD9910's state in a way that can't be recovered without a RESET.
                self.core.break_realtime()
                delay(5 * duration_of_write)

            # Configure RAM mode for this DDS. We'll use profile 0 for writing, but
            # it could be reconfigured later after the data has been stored.
            self.dds.set_profile_ram(
                start=offset, end=offset + len(data) - 1, profile=RAM_PROFILE
            )
            self.cpld.io_update.pulse_mu(8)  # assumes 8 mu > t_SYN_CCLK

            # Set the PROFILE pins to select the profile as a write target.
            # This affects all four DDSs but has no effect unless we pulse
            # IO_UPDATE.

            # This is a no-op since we are already on the right profile unless the
            # user has taken control themselves. So it's commented out with a check
            assert RAM_PROFILE == urukul.DEFAULT_PROFILE

            self.dds.write_ram(data)

            # Here we would restore ARTIQ's default profile setting, but it's not
            # needed, since we never changed

    @kernel
    def device_cleanup(self):
        """
        Return to normal mode after the experiment is finished

        Note that this is called once per experiment, not once per scan, so this
        does not free the user from having to cleanup after themselves, only
        prevents them from corrupting other experiments too.
        """
        self.device_cleanup_subfragments()

        self.core.break_realtime()
        self.disable_ram_mode()

    @kernel
    def _urukul_rst(self, cpld):
        """
        Reset all DDSs on the Urukul board

        This should not be done lightly! a) it will affect all the DDSs on this
        board and b) according to Sebastian it might result in an unrecoverable
        state that needs a power-cycle to fix (though I have never observed
        this).
        """
        # type:(CPLD) -> None

        """Pulse MASTER_RESET"""

        logger.warning("Resetting DDS")
        self.core.break_realtime()
        cpld.cfg_write(cpld.cfg_reg | (1 << CFG_RST))
        delay(100e-3)
        cpld.cfg_write(cpld.cfg_reg & ~(1 << CFG_RST))
        delay(2000e-3)


class FrequencyShapedPulse(_ShapedPulse):
    ram_modulation_mode = ad9910.RAM_DEST_FTW
    ram_nodwell_mode = 1  # This might be ignored... acording to the datasheet
    ram_ramp_mode = ad9910.RAM_MODE_CONT_RAMPUP
    # Have it ramp up and down

    def build_fragment(
        self, centre_frequency_param_handle: FloatParamHandle, ad9910_name=None
    ):
        """
        Requires you to pass a FloatParamHandle representing a parameter that
        the pulse's centre frequency will be bound to.
        """
        super().build_fragment(ad9910_name)

        self.centre_frequency = centre_frequency_param_handle

    @abc.abstractmethod
    def generate_frequencies(self, n_words) -> np.ndarray:
        """
        This function must be defined by the user to define their pulse shape.
        It must return a numpy array:
            * detuning_frequency: array of length n_words
        """

    @rpc
    def _get_ram_words(self) -> TList(TInt32):
        """
        Call the user-provided function to generate a new pulse shape of the
        given length, and return this to the core device as RAM tuning words.
        """
        detuning_frequency = self.generate_frequencies(self.num_steps.get())

        assert len(detuning_frequency) == self.num_steps.get()

        absolute_frequency = self.centre_frequency.get() + detuning_frequency
        # Need to ensure that we don't have frequencies out of the bound
        logger.warning(absolute_frequency)
        assert np.all(
            absolute_frequency < self.dds.ftw_to_frequency(0xFFFFFFFF)
        ), "Frequency too high"
        assert np.all(absolute_frequency > 0), "Frequency too low"

        # Convert to ram words
        ram_data = [np.int32(0x00)] * self.num_steps.get()
        self.dds.frequency_to_ram(frequency=absolute_frequency, ram=ram_data)

        return ram_data

    @kernel
    def prepare_pulse(self):
        """
        Prepare for playback of the sequence recorded in RAM

        This will enable RAM mode for this DDS - you cannot use it as a normal
        DDS until you call `disable_ram_mode`.

        You should call `trigger_pulse` after this to actually play the
        sequence, and call `disable_ram_mode` afterwards to clean up.
        """
        self._enter_RAM_mode()


class PhasorShapedPulse(_ShapedPulse):
    ram_modulation_mode = ad9910.RAM_DEST_POWASF

    @abc.abstractmethod
    def generate_amplitudes_and_phases(self, n_words) -> tuple[np.ndarray, np.ndarray]:
        """
        This function must be defined by the user to define their pulse shape.
        It must return a tuple of numpy arrays:
            * amplitude: array of length n_words, coerced to 0-1
            * phase: array of length n_words, coerced to 0-2*pi
        """

    @rpc
    def _get_ram_words(self) -> TList(TInt32):
        """
        Call the user-provided function to generate a new pulse shape of the
        given length, and return this to the core device as RAM tuning words.
        """
        amplitude, phases = self.generate_amplitudes_and_phases(self.num_steps.get())

        assert len(amplitude) == len(phases) == self.num_steps.get()

        # Coerce to 0-1 and 0-2pi
        pulse_amplitudes = np.clip(amplitude, 0, 1)
        pulse_phases = np.clip(phases, 0, 2 * np.pi)

        # Convert phases to turns
        pulse_turns = pulse_phases / (2 * np.pi)

        # Convert to ram words
        ram_data = [np.int32(0x00)] * self.num_steps.get()
        self.dds.turns_amplitude_to_ram(
            turns=pulse_turns, amplitude=pulse_amplitudes, ram=ram_data
        )

        return ram_data

    @kernel
    def prepare_pulse(self, frequency: float):
        """
        Prepare for playback of the sequence recorded in RAM

        This will enable RAM mode for this DDS - you cannot use it as a normal
        DDS until you call `disable_ram_mode`.

        You should call `trigger_pulse` after this to actually play the
        sequence, and call `disable_ram_mode` afterwards to clean up.

        Args:
            frequency (float): Centre frequency to be modulated by the RAM data.
        """
        # We must set the FTW of the DDS - this is distinct from the usual
        # frequency which is stored in a single-tone profile
        self.dds.set_frequency(frequency=frequency)

        self._enter_RAM_mode()


class BlackmanShapedPulse(PhasorShapedPulse):
    """
    Blackman shaped pulses (amplitude only)
    """

    def build_fragment(self, *args, **kwargs):
        self._old_num_steps = -1

        super().build_fragment(*args, **kwargs)

    def generate_amplitudes_and_phases(self, n_words) -> np.ndarray:
        """
        Use the Blackman window function to generate a smooth range of amplitudes

        The output will be normalized to 0 -> +1.
        """

        amplitude = np.blackman(n_words)
        phase = np.zeros_like(amplitude)

        return amplitude, phase

    @kernel
    def is_recalc_needed(self) -> bool:
        return_value = False

        if self.num_steps.get() != self._old_num_steps:
            return_value = True

        self._old_num_steps = self.num_steps.get()

        return return_value
