#!/usr/bin/env python3

import numpy as np
import pyqtgraph as pg
from artiq.applets.simple import TitleApplet
from PyQt5.QtCore import QTimer


class IJDPlot(pg.PlotWidget):
    def __init__(self, args, req):
        super().__init__()
        self.args = args
        self.timer = QTimer()
        self.timer.setSingleShot(True)
        self.timer.timeout.connect(self.length_warning)
        self.mismatch = {"X values": False}
        self.plotItem.setLabel("left", "Read Voltage (V)")
        x_label = args.x_label
        self.plotItem.setLabel("bottom", x_label)

    def data_changed(self, value, metadata, persist, mods, title):
        try:
            y = value[self.args.y]
        except KeyError:
            return
        x = value.get(self.args.x)
        if x is None:
            x = np.arange(len(y))

        if not len(y) or len(y) != len(x):
            self.mismatch["X values"] = True
        else:
            self.mismatch["X values"] = False
        if not any(self.mismatch.values()):
            self.timer.stop()
        else:
            if not self.timer.isActive():
                self.timer.start(1000)
            return

        self.clear()
        self.plot(x, y, pen=None, symbol="x")
        self.setTitle(title)
        if window_pars := value.get(self.args.window):
            self.add_window(x, window_pars)

    def length_warning(self):
        self.clear()
        text = "⚠️ dataset lengths mismatch:\n"
        errors = ", ".join([k for k, v in self.mismatch.items() if v])
        text = " ".join([errors, "should have the same length as Y values"])
        self.addItem(pg.TextItem(text))

    def add_window(self, x, window_pars):
        i_jump = window_pars[0]
        i_rise = window_pars[1]
        i_lock = window_pars[2]
        v_lock = window_pars[3]
        # success = window_pars[4]

        if i_jump >= len(x):
            i_jump = len(x) - 1

        if i_rise >= len(x):
            i_rise = 0

        jump_line = pg.InfiniteLine(pos=x[i_jump], angle=90)
        self.addItem(jump_line)

        rise_line = pg.InfiniteLine(pos=x[i_rise], angle=90)
        self.addItem(rise_line)

        marker = pg.ScatterPlotItem(
            pen="w",  # Color of the marker border
            brush="b",  # Fill color of the marker
            size=10,  # Size of the marker
        )
        marker.addPoints(x=[x[i_lock]], y=[v_lock])
        self.addItem(marker)

        crosshair = pg.CrosshairROI(pos=[x[i_lock], v_lock])

        lock_line_vertical = pg.InfiniteLine(
            pos=x[i_lock], angle=90, pen=pg.mkPen("r", width=2)
        )
        self.addItem(lock_line_vertical)
        lock_line_horizontal = pg.InfiniteLine(
            pos=v_lock, angle=0, pen=pg.mkPen("r", width=2)
        )
        self.addItem(lock_line_horizontal)

        lock_poin_text = pg.TextItem(
            f"Lock point: ({x[i_lock]:.2f}, {v_lock:.2f})", anchor=(0, 0), color="r"
        )
        lock_poin_text.setPos(x[i_lock], v_lock)
        self.addItem(lock_poin_text)


def main():
    applet = TitleApplet(IJDPlot)
    applet.add_dataset("y", "Y values")
    applet.add_dataset("x", "X values")
    applet.add_dataset("window", "Params defining injection window")
    applet.argparser.add_argument(
        "--x_label",
        help="Label for the X axis",
    )
    applet.run()


if __name__ == "__main__":
    main()
