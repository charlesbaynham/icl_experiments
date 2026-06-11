"""
This package provides a template experiment, :class:`~RedMOTWithExperimentBase` .
Unlike other modules, it *does not* provide a Fragment which you should use via
`self.setattr_fragment`. Instead, it defines an :class:`~ExpFragment` which should be
converted into an :class:`~EnvExperiment` using :meth:`~make_fragment_scan_exp`.

The :class:`~ExpFragment`s that this module defines cannot be used without some
customization first. The :meth:`~build_fragment`, :meth:`~device_setup` and
:meth:`~run_once` methods of these :class:`ExpFragment` s contain "hooks" -
methods which can (or sometimes must) be implemented by child classes to alter
the functionality of these experiment. This allows you to reuse this code for
multiple different experiments by implementing child classes which define these
hooks in different ways.

For example, see the documentation of :class:`~RedMOTWithExperimentBase` for the
most basic implementation of hooks.

Mixins
------

This structure of overriding methods allows the use of "mixins". These are
classes which implement various pieces of functionality, which can be selected
from when authoring an experiment.

For example, you might author a mixin that adds imaging with the Andor camera
and another which causes atoms to be trapped in a lattice at the end of the MOT.
Your experiment might then inherit from both of these, to use both features at
the same time::

    from somewhere import AndorImagingMixin, LatticeTrappingMixin


    class MyAndorImagedLatticeExperiment(
        AndorImagingMixin,
        LatticeTrappingMixin,
        RedMOTWithExperimentBase
    ):
        pass

"""

import logging

import numpy as np
from artiq.coredevice.core import Core
from artiq.coredevice.dma import CoreDMA
from artiq.language import kernel
from artiq.language import now_mu
from artiq.language import portable
from ndscan.experiment import Fragment
from ndscan.experiment.parameters import BoolParam
from ndscan.experiment.parameters import BoolParamHandle
from numpy import int32
from numpy import int64

from repository.lib.utils import FastIntChecksum

logger = logging.getLogger(__name__)

BUFFER_DEPTH = 300

# The pulse record stores physical quantities (frequencies in Hz, the delivery
# setpoint in V) that are genuinely floats, alongside a few integer-valued
# fields (direction, machine-unit times). They are all stored as float64, which
# represents the integer fields exactly while preserving full precision for the
# floats. The per-shot dedup checksum, however, needs integers, so values are
# scaled by this factor and rounded before being fed to the integer checksum.
# This keeps the checksum sensitive to sub-unit changes (e.g. a sub-volt
# setpoint change) that an int64 cast would otherwise hide.
CHECKSUM_SCALE = 1000


class PulseDMARecording(Fragment):
    dma_name = "actions_after_drop"

    def build_fragment(self, outer_self: "DipoleTrapWithExperimentBase"):
        self.outer_self = outer_self

        self.setattr_device("core")
        self.core: Core

        self.setattr_device("core_dma")
        self.core_dma: CoreDMA

        self.setattr_param(
            "enable_pulse_sequence_storage",
            BoolParam,
            description="Store recorded pulse sequences in results",
            default=True,
        )
        self.enable_pulse_sequence_storage: BoolParamHandle

        self.dma_handle = (int32(0), int64(0), int32(0), False)
        self.dma_handle_valid = False

        # Preallocate a buffer to record pulses
        self._pulse_record_start_times_mu = [int64(0)] * BUFFER_DEPTH
        self._pulse_record_durations_mu = [int64(0)] * BUFFER_DEPTH
        self._pulse_record_directions = [int32(0)] * BUFFER_DEPTH
        # Frequencies stored as float Hz; saved as int64 Hz in the OpaqueChannel
        self._pulse_record_opll_freq_hz = [0.0] * BUFFER_DEPTH
        self._pulse_record_switch_freq_hz = [0.0] * BUFFER_DEPTH
        self._pulse_record_delivery_freq_hz = [0.0] * BUFFER_DEPTH
        self._pulse_record_delivery_setpoint = [0.0] * BUFFER_DEPTH
        self._pulse_record_num_pulses = 0
        self._pulse_record_checksum = int64(0)

        # Checksummer object
        self.checksummer = FastIntChecksum(seed=0)

    def host_setup(self):
        # Create the broadcast dataset for live monitoring. archive=False avoids
        # h5py ragged-array errors; host_cleanup encodes it to flat arrays for archiving.
        self.set_dataset("pulse_record", [], broadcast=True, archive=False)
        super().host_setup()

    @kernel
    def record_pulse_sequence(self):
        # Wipe the buffer; register_pulse() repopulates it during recording
        self._pulse_record_num_pulses = 0
        with self.core_dma.record(self.dma_name):
            self.outer_self.actions_after_drop()
        self._save_pulse_sequence_to_dataset()

    @kernel
    def _save_pulse_sequence_to_dataset(self):
        """
        Save the recorded pulse sequence to the pulse_record dataset.

        ARTIQ can't handle dicts etc, so we wrap this into a 2D array. ARTIQ
        also requires that array to be homogeneously typed, so every row is
        stored as float64: the integer-valued fields (direction, machine-unit
        times) are exactly representable, and the physical quantities
        (frequencies in Hz, setpoint in V) keep their full precision.
        """

        SAME_AS_LAST_TIME_SENTINEL = -1.0
        DISABLED_SENTINEL = -2.0

        if not self.enable_pulse_sequence_storage.get():
            self.append_to_dataset("pulse_record", [[DISABLED_SENTINEL]])
            return

        directions = [
            float(x)
            for x in self._pulse_record_directions[: self._pulse_record_num_pulses]
        ]
        start_times_mu = [
            float(x)
            for x in self._pulse_record_start_times_mu[: self._pulse_record_num_pulses]
        ]
        durations_mu = [
            float(x)
            for x in self._pulse_record_durations_mu[: self._pulse_record_num_pulses]
        ]
        opll_hz = [
            float(x)
            for x in self._pulse_record_opll_freq_hz[: self._pulse_record_num_pulses]
        ]
        switch_hz = [
            float(x)
            for x in self._pulse_record_switch_freq_hz[: self._pulse_record_num_pulses]
        ]
        delivery_hz = [
            float(x)
            for x in self._pulse_record_delivery_freq_hz[
                : self._pulse_record_num_pulses
            ]
        ]
        delivery_setpoint = [
            float(x)
            for x in self._pulse_record_delivery_setpoint[
                : self._pulse_record_num_pulses
            ]
        ]

        pulse_record = [
            directions,
            start_times_mu,
            durations_mu,
            opll_hz,
            switch_hz,
            delivery_hz,
            delivery_setpoint,
        ]

        # Calculate a checksum of this pulse record. The checksum needs
        # integers, so each (float) value is scaled before the int64 cast - this
        # keeps it sensitive to sub-unit changes (e.g. a sub-volt setpoint
        # change) that an unscaled int64 cast would hide.
        checksum = int64(0)
        for i in range(7):
            self.checksummer.set_seed(checksum)
            checksum = self.checksummer.checksum(
                [int64(x * CHECKSUM_SCALE) for x in pulse_record[i]]
            )

        if checksum != self._pulse_record_checksum:
            # Record the updated pulse sequence
            self.append_to_dataset("pulse_record", pulse_record)
        else:
            # Save the sentinel value for "same as last time"
            self.append_to_dataset("pulse_record", [[SAME_AS_LAST_TIME_SENTINEL]])

        self._pulse_record_checksum = checksum

    @kernel
    def DMA_initialization_hook_after_drop(self):
        self.dma_handle = self.core_dma.get_handle(self.dma_name)
        self.dma_handle_valid = True

    @kernel
    def playback(self):
        if not self.dma_handle_valid:
            raise RuntimeError(
                "DMA buffer handle not set. Did you forget to call DMA_initialization_hook_after_drop?"
            )
        return self.core_dma.playback_handle(self.dma_handle)

    @portable
    def register_pulse(self, is_up: bool, duration_s: float):
        """
        Register a clock pulse about to be applied.

        Call this IMMEDIATELY BEFORE turning the clock AOM on so the
        pulse start timestamp and duration are recorded together. Host
        code can then reconstruct whichever effective timing model it
        needs from the full sequence record.
        """

        if self._pulse_record_num_pulses >= BUFFER_DEPTH:
            raise RuntimeError(
                "Exceeded maximum number of pulses that can be recorded. Congratulations!!!"
            )

        duration_mu = self.core.seconds_to_mu(duration_s)
        t_now_mu = now_mu()

        self._pulse_record_start_times_mu[self._pulse_record_num_pulses] = t_now_mu
        self._pulse_record_durations_mu[self._pulse_record_num_pulses] = duration_mu
        self._pulse_record_directions[self._pulse_record_num_pulses] = int32(
            1 if is_up else 0
        )
        # Report the OPLL frequency at the centre of the pulse
        self._pulse_record_opll_freq_hz[self._pulse_record_num_pulses] = (
            self.outer_self._get_opll_instantaneous(t_now_mu)
            + self.outer_self._get_opll_instantaneous(t_now_mu + duration_mu)
        ) / 2.0
        self._pulse_record_switch_freq_hz[self._pulse_record_num_pulses] = (
            self.outer_self._tracked_up_switch_freq
            if is_up
            else self.outer_self._tracked_down_switch_freq
        )
        self._pulse_record_delivery_freq_hz[self._pulse_record_num_pulses] = (
            self.outer_self._tracked_delivery_aom_freq
        )
        self._pulse_record_delivery_setpoint[self._pulse_record_num_pulses] = (
            self.outer_self._tracked_delivery_aom_setpoint
        )
        self._pulse_record_num_pulses += 1

    def host_cleanup(self):
        self._archive_encoded_pulse_records()
        super().host_cleanup()

    def _archive_encoded_pulse_records(self):
        """Encode accumulated pulse records as flat float64 arrays and archive them.

        Reads records from the ``pulse_record`` broadcast dataset and writes two
        archivable datasets:

        - ``pulse_record_flat``: concatenation of all per-record flat arrays.
        - ``pulse_record_offsets``: starting index in ``pulse_record_flat`` for each
          record, allowing the original records to be reconstructed.

        Each record is encoded as a flat 1D array:

        - Sentinel record (``[[sentinel_value]]``): ``[sentinel_value]`` (length 1)
        - Regular record (7 rows of ``num_pulses`` values each):
          ``[num_pulses, dir_0, …, start_0, …, dur_0, …, opll_0, …, switch_0, …, delivery_0, …, setpoint_0, …]``
          (length ``1 + 7 * num_pulses``)

        Frequencies are in Hz and the setpoint is in V, both stored at full
        float precision. The machine-unit times and the direction/num_pulses
        fields are integer-valued but stored as float64 like everything else.
        """
        records = self.get_dataset("pulse_record", archive=False)
        if not records:
            return

        flat_data = []
        offsets = []
        current_offset = 0

        for record in records:
            offsets.append(current_offset)
            if len(record) == 1 and len(record[0]) == 1:
                flat_data.append(float(record[0][0]))
                current_offset += 1
            else:
                num_pulses = len(record[0])
                flat_data.append(float(num_pulses))
                for row in record:
                    flat_data.extend(float(x) for x in row)
                current_offset += 1 + 7 * num_pulses

        self.set_dataset(
            "pulse_record_flat",
            np.array(flat_data, dtype=np.float64),
            broadcast=False,
            archive=True,
        )
        self.set_dataset(
            "pulse_record_offsets",
            np.array(offsets, dtype=np.int64),
            broadcast=False,
            archive=True,
        )
