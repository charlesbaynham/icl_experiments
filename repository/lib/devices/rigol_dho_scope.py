from generic_scpi_driver.session import Session


class _RawSerialInstance(Session):
    def __init__(self, id, **kwargs):
        id_resolved = get_com_port_by_hwid(id)
        logger.debug("Resolved serial port ID %s to %s", id, id_resolved)
        self.ser = Serial(id_resolved, 115200, timeout=1)

    def close(self):
        self.ser.close()
        self.ser = None

    def flush(self, *args, **kwargs):
        pass

    def write(self, msg):
        """Send a message without waiting for a reply"""
        if self.ser is None:
            raise RuntimeError("This controller has been closed")

        self.ser.write(b"%s\n" % msg.encode())

    def query(self, msg):
        """Send a message and return the reply"""
        self.write(msg)

        # This device repeats the command before it replies for some reason,
        # so ignore the first line
        # _ = self.ser.readline()
        line = self.ser.readline()
        rtn = line.decode().strip()
        return rtn

    def read_line(self):
        line = self.ser.readline()
        return line.decode()
