"""
RAM MODULATION MODE

The RAM modulation mode (see Figure 23) is activated via the RAM enable bit and
assertion of the I/O_UPDATE pin (or a profile change). In this mode, the
modulated DDS signal control parameters are supplied directly from RAM. The RAM
consists of 32-bit words and is 1024 words deep. Coupled with a sophisticated
internal state machine, the RAM provides a very flexible method for generating
arbitrary, time dependent waveforms. A programmable timer controls the rate at
which words are extracted from the RAM for delivery to the DDS. Thus, the
programmable timer establishes a sample rate at which 32-bit samples are
supplied to the DDS

The selection of the specific DDS signal control parameters that serve as the
destination for the RAM samples is also programmable through eight independent
RAM profile registers. Select a par- ticular profile using the three external
profile pins (PROFILE[2:0]). A change in the state of the profile pins with the
next rising edge on SYNC_CLK activates the selected RAM profile. In RAM
modulation mode, the ability to generate a time depen- dent amplitude, phase, or
frequency signal enables modulation of any one of the parameters controlling the
DDS carrier signal. Furthermore, a polar modulation format is available that
partitions each RAM sample into a magnitude and phase component; 16 bits are
allocated to phase and 14 bits are allocated to magnitude.

<...>

RAM CONTROL
===========

RAM Overview
------------

The AD9910 makes use of a 1024 × 32-bit RAM. The RAM has two fundamental modes
of operation: data load/retrieve mode and playback mode. Data load/retrieve mode
is active when the RAM data is being loaded or read back via the serial I/O
port. Playback mode is active when the RAM enable contents are routed to one of
the internal data destinations. Depending on the specific playback mode, the
user can partition the RAM with up to eight independent time domain waveforms.
These waveforms drive the DDS signal control parameters, allowing for frequency,
phase, amplitude, or polar modulated signals. RAM operations are enabled by
setting the RAM enable bit in Control Function Register 1; an I/O update (or a
profile change) is necessary to enact any change to the state of this bit.
Waveforms are generated using eight RAM profile control registers that are
accessed via the three profile pins. Each profile contains the following: 
10-bit waveform start address word  10-bit waveform end address word  16-bit
address step rate control word  3-bit RAM mode control word  No-dwell high bit
 Zero-crossing bit The user must ensure that the end address is greater than
the start address. Each profile defines the number of samples and the sample
rate for a given waveform. In conjunction with an internal state machine, the
RAM contents are delivered to the appropriate DDS signal control parameter(s) at
the specified rate. Further- more, the state machine can control the order in
which samples are extracted from RAM (forward/reverse), facilitating efficient
generation of time symmetric waveforms.

Load/Retrieve RAM Operation
---------------------------

It is strongly recommended that RAM enable = 0 when performing RAM load/retrieve
operations. Loading or retrieving the contents of the RAM requires a three-step
process.
    1. Program the RAM Profile 0 through RAM Profile 7 control
    registers with the start and end addresses that are to define the boundaries
    of each independent waveform. 2. Drive the appropriate logic levels on the
    profile pins to select the desired RAM profile 3. Write to (or read from)
    the RAM ( Address 0x16) the appropriate number of RAM words as specified by
    the selected RAM profile control register (see the Serial Programming
    section for details). Figure 41 is a block diagram showing the functional
    components used for RAM data load/retrieve operation.
During RAM load/retrieve operations, the state machine controls an up/down
counter to step through the required RAM loca- tions. The counter synchronizes
with the serial I/O port so that the serial/parallel conversion of the 32-bit
words is correctly timed with the generation of the appropriate RAM address to
properly execute the desired read or write operation.

<Figure 41.> RAM Data Load/Retrieve Operation

The RAM profiles are completely independent; it is possible to define
overlapping address ranges. Doing so causes data that has been written to
overlapped address locations to be overwritten by the most recent write
operation.

Multiple waveforms can be loaded into RAM by treating them as a single waveform,
that is, a time-domain concatenation of all the waveforms. This is done by
programming one of the RAM profiles with a start and end address spanning the
entire range of the concatenated waveforms. Then the single concatenated
waveform is written into RAM via the serial I/O port using the same RAM profile
that was programmed with the start and end addresses. The RAM profiles must then
be programmed with the proper start and end addresses associated with each
individual waveform.

RAM Playback Operation (Waveform Generation)
---------------------------------------------

When the RAM has been loaded with the desired waveform data, it can then be used
for waveform generation during play back. RAM playback requires that RAM enable
= 1. To play back RAM data, select the desired waveform using the PROFILE[2:0]
pins. The selected profile directs the internal state machine by defining the
RAM address range occupied by the waveform, the rate at which samples are to be
extracted from the RAM (playback rate), the mode of operation, and whether to
use the no-dwell feature. Figure 42 is a block diagram showing the functional
components used for RAM playback operation

<Figure 42>. RAM Playback Operation

During playback, the state machine uses an up/down counter to step through the
specified address locations. The clock rate of this counter defines the playback
rate, that is, the sample rate of the generated waveform. The clocking of the
counter is controlled by a 16-bit programmable timer that is internal to the
state machine. This timer is clocked by the DDS clock, and its time interval is
set by the 16-bit address step rate value stored in the selected RAM profile
register. The address step rate value determines the playback rate. For example,
if M is the 16-bit value of the address step rate for a specific RAM profile,
then the playback rate for that profile is given by

rate = f_DDSCLOCK / M = f_SYSCLOCK / (4M)

The sample interval (Δt) associated with the playback rate is therefore given by

Δt = 1 / rate = 4M / f_SYSCLOCK

RAM data entry/retrieval via the I/O port takes precedence over playback
operation. An I/O operation targeting the RAM during playback interrupts any
waveform in progress. The 32-bit words output by the RAM during playback route
to the DDS signal control parameters according to two RAM playback destination
bits in Control Function Register 1. The 32-bit words are partitioned based on
Table 12.

| CFR1[30:29] | DDS Signal Control Parameter | Bits assigned to DDS parameters |
|-------------|------------------------------|---------------------------------|
| 00          | Frequency                    | 31:0                            |
| 01          | Phase                        | 31:16                           |
| 10          | Amplitude                    | 31:18                           |
| 11          | Polar (phase and amplitude)  | 31:16 (phase), 15:2 (amplitude) |

When the destination is phase, amplitude, or polar, the unused LSBs are ignored.

The RAM playback destination bits affect specific DDS signal control parameters.
The parameters that are not affected by the RAM playback destination bits are
controlled by the FTW, POW, and/or ASF registers.

RAM_SWP_OVR (RAM Sweep Over) Pin
---------------------------------

The RAM_SWP_OVR pin provides an active high external signal that indicates the
end of a playback sequence. The operation of this pin varies with the RAM
operating mode as detailed in the following sections. When RAM enable = 0, this
pin is forced to a Logic 0. Overview of RAM Playback Modes The RAM can operate
in any one of five different playback modes.  Direct switch  Ramp-up 
Bidirectional ramp  Continuous bidirectional ramp  Continuous recirculate The
mode is selected via the 3-bit RAM mode control word located in each of the RAM
profile registers. Thus, the RAM operating mode is profile dependent. The RAM
profile mode control bits are detailed in Table 13.

| RAM Mode Control Bits | RAM operating mode              |
|-----------------------|----------------------------------|
| 000, 101, 110, 111    | Direct switch                    |
| 001                   | Ramp-up                          |
| 010                   | Bidirectional ramp               |
| 011                   | Continuous bidirectional ramp    |
| 100                   | Continuous recirculate           |


CFAB Notes
==========

Based on the above, I think I need to two these things:

0. Set RAM_ENABLE = 0 in CFR1.
1. Set the PROFILE pins to select a RAM profile. This will affect ALL DDSs on
   the Urukul, but won't do anything unless I pulse IO_UPDATE.
2. Write my RAM profile settings into the appropriate RAM profile control
   register. ARTIQ uses profile "7" by default, so let's use profile 0.
3. Step 2 specified how many 32-bit words I need to generate. Do so.
4. Write all these words into address "0x16" which will write them into the RAM,
   starting at the offset specified in the RAM profile control register.

When I want to playback the RAM, I need to:

1. Set RAM_ENABLE = 1 in CFR1.
2. Pulse IO_UPDATE to start the RAM playback. If I want, I can mask this using
   NU_MASK to only affect the DDS I want to affect. I probably want to do this.


Note that the AD9910 assumed that I have full control over the RAM PROFILE bits,
but I don't: the Urukul CPLD ties all the PROFILE lines together so I can't
independently control them. I have two options:

1. Mess around with NU_MASK to only affect the DDS I want to affect.
2. Don't use the PROFILE bits for RAM playback and use the "RAM Internal Profile Control Modes" instead.

For this demo code, I'll do neither and just leave all the other DDSs off.

Note that the RAM profiles and single-tone profiles use the same registers: the interpretation
of these registers depends on the RAM_ENABLE bit in CFR1.
"""

import logging

import numpy as np
from artiq.coredevice.ad9910 import AD9910, RAM_MODE_RAMPUP
from artiq.coredevice.core import Core
from artiq.coredevice.urukul import CPLD
from artiq.experiment import EnumerationValue
from artiq.experiment import EnvExperiment
from artiq.experiment import delay
from artiq.experiment import kernel
from pyaion.lib.utils import get_local_devices

logger = logging.getLogger(__name__)

RAM_PROFILE = 0


class AD9910RAMTest(EnvExperiment):
    def build(self):
        self.setattr_device("core")
        self.core: Core

        ad9910_devices = get_local_devices(self, AD9910)

        self.setattr_argument(
            "dds_name", EnumerationValue(ad9910_devices, default="urukul8_ch2")
        )

        self.dds: AD9910 = self.get_device(self.dds_name)
        self.cpld: CPLD = self.dds.cpld

    def prepare(self):
        # Hard-code parameters for now
        # self.att = 30
        # self.freq = 30e6

        self.n_steps = 10

        self.ram_data = np.int32(list(range(self.n_steps))).tolist()

        # self.phase_start = 0.0
        # self.phase_end = 0.0
        # self.phases = np.linspace(self.phase_start, self.phase_end, self.n_steps)

        # self.amp_start = 0.0
        # self.amp_end = 1.0
        # self.amps = np.linspace(self.amp_start, self.amp_end, self.n_steps)

    @kernel
    def run(self):
        self.core.reset()
        delay(1e-3)
        self.dds.init(blind=False)

        # Configure RAM mode - this will affect all four DDSs on the Urukul
        self.dds.set_profile_ram(
            start=0x00, end=self.n_steps - 1, mode=RAM_MODE_RAMPUP, profile=RAM_PROFILE
        )
        self.cpld.set_profile(RAM_PROFILE)

        # Note that I'm not setting CFR1 to enable RAM mode, so these settings
        # don't affect the DDS output yet, they're just read in and out as a test.

        self.read_and_print_ram()

        # Write to RAM
        logger.info("Writing %s", self.ram_data)
        self.core.break_realtime()
        self.dds.write_ram(self.ram_data)

        # Read it back
        self.read_and_print_ram()

    @kernel
    def read_and_print_ram(self):
        self.core.break_realtime()
        read_data = [np.int32(0x00)] * self.n_steps
        self.dds.read_ram(read_data)

        logger.info("RAM contents: %s", read_data)
