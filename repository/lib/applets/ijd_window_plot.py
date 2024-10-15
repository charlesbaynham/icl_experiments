#!/usr/bin/env python3

import numpy as np
import PyQt5  # make sure pyqtgraph imports Qt5
import pyqtgraph
import pyqtgraph as pg
from artiq.applets.simple import TitleApplet
from PyQt5.QtCore import QTimer


class IJDPlot(pyqtgraph.PlotWidget):
    def __init__(self, args, req):
        pyqtgraph.PlotWidget.__init__(self)
        self.args = args
        self.timer = QTimer()
        self.timer.setSingleShot(True)
        self.timer.timeout.connect(self.length_warning)
        self.mismatch = {"X values": False}

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
        if self.args.window:
            self.add_window()

    def length_warning(self):
        self.clear()
        text = "⚠️ dataset lengths mismatch:\n"
        errors = ", ".join([k for k, v in self.mismatch.items() if v])
        text = " ".join([errors, "should have the same length as Y values"])
        self.addItem(pyqtgraph.TextItem(text))

    def add_window(self):
        window_pars = self.args.window
        i_jump = window_pars[0]
        i_rise = window_pars[1]
        i_lock = window_pars[2]
        v_lock = window_pars[3]
        # success = window_pars[4]

        jump_line = pg.InfiniteLine(pos=i_jump, angle=90)
        self.addItem(jump_line)

        rise_line = pg.InfiniteLine(pos=i_rise, angle=0)
        self.addItem(rise_line)

        marker = pg.ScatterPlotItem(
            pen="w",  # Color of the marker border
            brush="b",  # Fill color of the marker
            size=10,  # Size of the marker
        )
        marker.addPoints([pg.Point(i_lock, v_lock)])
        self.addItem(marker)


def main():
    applet = TitleApplet(IJDPlot)
    applet.add_dataset("y", "Y values")
    applet.add_dataset("x", "X values", required=False)
    applet.add_dataset("window", "Params defining injection window", required=False)
    applet.run()


if __name__ == "__main__":
    main()
