"""
Monitor temperatures with an 8-channel Brainbox ED-593
"""

import logging

from qbutler.calibration import Calibration
from qbutler.calibration import CalibrationResult

logger = logging.getLogger(__name__)

import select
import socket
import time


class AsciiIo:
    """Example class for communication with Brainboxes ED-range products
    Tested with Python 2.7.9 and 3.4.3 on Windows, and 2.7.6 and 3.4.0 on Linux
    """

    def __init__(self, ipaddr, port=9500, timeout=5.0):
        self.sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self.sock.connect((ipaddr, port))
        self.timeout = timeout
        self.recv_chunk_size = 32

    def command_noresponse(self, txmessage):
        self._send(txmessage)

    def command_response(self, txmessage):
        self._send(txmessage)
        return self._receive()

    def _send(self, txmessage):
        txmessage = txmessage + b"\r"
        totalsent = 0
        while totalsent < len(txmessage):
            bytes_sent = self.sock.send(txmessage[totalsent:])
            if bytes_sent == 0:
                raise RuntimeError("socket connection broken")
            totalsent = totalsent + bytes_sent

    def _receive(self):
        tstart = time.time()
        data = b""
        endpos = -1
        while endpos < 0:
            tleft = max(0.0, tstart + self.timeout - time.time())
            ready_to_read, ready_to_write, in_error = select.select(
                [self.sock], [], [self.sock], tleft
            )
            if len(in_error) > 0:
                raise RuntimeError("error on socket connection")
            if len(ready_to_read) > 0:
                chunk = self.sock.recv(self.recv_chunk_size)
                if chunk == b"":
                    raise RuntimeError("socket connection broken")
                data = data + chunk
                endpos = data.find(b"\r")
            elif tleft == 0.0:
                # raise RuntimeError("timeout on socket receive")
                return None
        return data[:endpos]

    def _destructor(self):
        try:
            self.sock.shutdown(socket.SHUT_RDWR)
            self.sock.close()
        except:
            # ignore any failures to shutdown and close the socket - it's probably already closed
            pass

    def __del__(self):
        self._destructor()

    def __enter__(self):
        return self

    def __exit__(self, type, value, traceback):
        self._destructor()  # __del__ gets called anyway, so does this help at all?  Does it get the socket closed sooner?


def get_temperatures(ipaddr):
    with AsciiIo(ipaddr=ipaddr, port=9500, timeout=1.0) as io:
        rxdata = io.command_response(b"#01")
        if rxdata is None:
            raise RuntimeError("No response received!")
        else:
            temperatures = [float(x) for x in rxdata.decode()[2:].split("+")]

            # If the temperature is over 9999 it means the channel is not
            # connected, so mark it with a NaN
            for index, temperature in enumerate(temperatures):
                if temperature > 9999:
                    temperatures[index] = float("nan")

            return temperatures


class _MonitorLabTemperatureBrainbox(Calibration):
    """
    Monitor the temperature of the lab with a Brainbox ED-593
    """

    monitor_ip = None

    descriptions = dict()
    "A dictionary of channel numbers to text descriptions, to be saved in the database"

    def temperature_string_parser(self, temperature_string):
        return float(temperature_string)

    def __init__(self, managers_or_parent, *args, **kwargs):
        if self.monitor_ip is None or not self.descriptions:
            raise NotImplementedError(
                "You must subclass this class and define 'monitor_ip' and 'descriptions"
            )

        super().__init__(managers_or_parent, *args, **kwargs)

    def build_calibration(self):
        self.set_timeout(30)

    def check_own_state(self):
        temperatures = get_temperatures(self.monitor_ip)

        logger.debug("Temperatures = %s", temperatures)

        measurements = []
        for index, description in self.descriptions.items():
            measurements.append(
                {
                    "tags": {"sensor": description, "type": "temperature"},
                    "fields": {"value": temperatures[index]},
                }
            )

        return CalibrationResult.OK, measurements


class MonitorTemperatureSidearmBrainbox(_MonitorLabTemperatureBrainbox):
    monitor_ip = "brainbox-temperature-10.137.3.254"
    descriptions = {
        6: "above_chamber",
    }
