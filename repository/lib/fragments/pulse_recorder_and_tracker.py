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
        self._pulse_record_beam_dds_freq_hz = [0.0] * BUFFER_DEPTH
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
    def device_setup(self):
        self.device_setup_subfragments()

        # Wipe the buffer. The new recording run will overwrite the old data
        self._pulse_record_num_pulses = 0

        # Record the actions_after_drop sequence in DMA
        # TODO should not recalculate every shot?  maybe?
        with self.core_dma.record(self.dma_name):
            self.outer_self.actions_after_drop()

        self._save_pulse_sequence_to_dataset()

    @kernel
    def _save_pulse_sequence_to_dataset(self):
        """
        Save the recorded pulse sequence to the pulse_record dataset.

        ARTIQ can't handle dicts etc, so we wrap this into a 2D array.
        This forces us to store directions as int64s which is wasteful,
        but oh well.
        """

        SAME_AS_LAST_TIME_SENTINEL = -1
        DISABLED_SENTINEL = -2

        if not self.enable_pulse_sequence_storage.get():
            self.append_to_dataset("pulse_record", [[DISABLED_SENTINEL]])
            return

        directions = [
            int64(x)
            for x in self._pulse_record_directions[: self._pulse_record_num_pulses]
        ]
        start_times_mu = [
            int64(x)
            for x in self._pulse_record_start_times_mu[: self._pulse_record_num_pulses]
        ]
        durations_mu = [
            int64(x)
            for x in self._pulse_record_durations_mu[: self._pulse_record_num_pulses]
        ]
        opll_hz = [
            int64(x)
            for x in self._pulse_record_opll_freq_hz[: self._pulse_record_num_pulses]
        ]
        beam_hz = [
            int64(x)
            for x in self._pulse_record_beam_dds_freq_hz[
                : self._pulse_record_num_pulses
            ]
        ]

        pulse_record = [
            directions,
            start_times_mu,
            durations_mu,
            opll_hz,
            beam_hz,
        ]

        # Calculate a checksum of this pulse record
        checksum = int64(0)
        for i in range(5):
            self.checksummer.set_seed(checksum)
            checksum = self.checksummer.checksum([int64(x) for x in pulse_record[i]])

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
        self._pulse_record_beam_dds_freq_hz[self._pulse_record_num_pulses] = (
            self.outer_self._tracked_up_dds_freq
            if is_up
            else self.outer_self._tracked_down_dds_freq
        )
        self._pulse_record_num_pulses += 1

    def host_cleanup(self):
        self._archive_encoded_pulse_records()
        super().host_cleanup()

    def _archive_encoded_pulse_records(self):
        """Encode accumulated pulse records as flat int64 arrays and archive them.

        Reads records from the ``pulse_record`` broadcast dataset and writes two
        archivable datasets:

        - ``pulse_record_flat``: concatenation of all per-record flat arrays.
        - ``pulse_record_offsets``: starting index in ``pulse_record_flat`` for each
          record, allowing the original records to be reconstructed.

        Each record is encoded as a flat 1D array:

        - Sentinel record (``[[sentinel_value]]``): ``[sentinel_value]`` (length 1)
        - Regular record (5 rows of ``num_pulses`` values each):
          ``[num_pulses, dir_0, …, start_0, …, dur_0, …, opll_0, …, beam_0, …]``
          (length ``1 + 5 * num_pulses``)
        """
        records = self.get_dataset("pulse_record")
        if not records:
            return

        flat_data = []
        offsets = []
        current_offset = 0

        for record in records:
            offsets.append(current_offset)
            if len(record) == 1 and len(record[0]) == 1:
                flat_data.append(int(record[0][0]))
                current_offset += 1
            else:
                num_pulses = len(record[0])
                flat_data.append(num_pulses)
                for row in record:
                    flat_data.extend(int(x) for x in row)
                current_offset += 1 + 5 * num_pulses

        self.set_dataset(
            "pulse_record_flat",
            np.array(flat_data, dtype=np.int64),
            broadcast=False,
            archive=True,
        )
        self.set_dataset(
            "pulse_record_offsets",
            np.array(offsets, dtype=np.int64),
            broadcast=False,
            archive=True,
        )
