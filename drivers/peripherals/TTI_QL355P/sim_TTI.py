"""
Define a basic simulation device which simulates the VISA response of a real device
"""

TOLERANCE = "5"  # 5 decimal places


class SimTTI:

    current = None
    voltage = None
    range = None

    def __init__(self):
        self.reset()

    def reset(self):
        self.current = 0
        self.voltage = 0
        self.range = 0

    def close(self):
        pass

    def write(self, cmd):
        args = cmd.split(" ")
        if args[0] == "i1":
            self.set_current(float(args[1]))
        elif args[0] == "v1":
            self.set_voltage(float(args[1]))
        elif args[0] == "range1":
            self.set_range(args[1])
        elif args[0] == "reset":
            self.reset()

    def query(self, cmd):
        if cmd == "i1?":
            return ("i1 {:." + TOLERANCE + "f}").format(self.current)
        elif cmd == "v1?":
            return ("v1 {:." + TOLERANCE + "f}").format(self.voltage)
        elif cmd == "range1?":
            return "range1 {}".format(self.get_range())

    def set_range(self, range):
        range_num = int(range)
        if range_num not in [0, 1, 2]:
            return
        self.range = range_num

    def get_range(self):
        return str(self.range)

    def set_current(self, current):
        if (
            (self.range == 2 and current > 0.5)
            or (self.range == 1 and current > 3)
            or (self.range == 0 and current > 5)
        ):
            return

        self.current = current

    def set_voltage(self, voltage):
        if (
            (self.range == 2 and voltage > 35)
            or (self.range == 1 and voltage > 35)
            or (self.range == 0 and voltage > 15)
        ):
            return

        self.voltage = voltage
