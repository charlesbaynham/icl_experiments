from PyQt5 import QtGui, QtCore
from PyQt5.QtWidgets import (
    QVBoxLayout,
    QWidget,
    QPushButton,
    QDialog,
    QDockWidget,
    QSizePolicy,
    QFrame,
    QMainWindow,
    QCheckBox,
)
from PyQt5.QtCore import Qt
import PyQt5
import pyqtgraph as pg
import pyqtgraph
import numpy as np
from artiq.applets.simple import SimpleApplet
import matplotlib.pyplot as plt
from simple_img_applet import SimpleImageViewer
from scipy.optimize import curve_fit


class ImageViewerWithSlices(QMainWindow):
    def __init__(self, args, req):
        super().__init__()
        self.args = args
        self.image_view = SimpleImageViewer(args, req)
        self.image_view.ui.histogram.hide()
        self.initUI()
        self.fitting = False
        self.image_view.ui.menuBtn

    def initUI(self):

        self.setCentralWidget(self.image_view)
        self.createDockWidgets()
        self.image_view.setSizePolicy(QSizePolicy.Minimum, QSizePolicy.Expanding)
        self.setSizePolicy(QSizePolicy.Minimum, QSizePolicy.Expanding)
        self.setGeometry(100, 100, 1000, 700)
        self.resizeDocks(
            [self.findChild(QDockWidget, "Left Dock")], [200], Qt.Horizontal
        )
        self.resizeDocks([self.findChild(QDockWidget, "Top Dock")], [200], Qt.Vertical)
        # self.resizeDocks([self.findChild(QDockWidget, "Bottom Dock")], [100], Qt.Vertical)

    def createDockWidgets(self):

        self.settings_dock = QDockWidget("Settings", self)
        settings_layout = QVBoxLayout()
        settings_widget = QFrame()
        settings_widget.setLayout(settings_layout)
        self.settings_dock.setWidget(settings_widget)
        self.addDockWidget(Qt.TopDockWidgetArea, self.settings_dock)
        # self.settings_dock.setSizePolicy(QSizePolicy.Minimum, QSizePolicy.Minimum)
        self.fit_check = QCheckBox("Gauss fit?")
        settings_layout.addWidget(self.fit_check)
        self.fit_check.stateChanged.connect(self.check_fit_state)

        self.top_dock = QDockWidget("Top Dock", self)
        self.top_plot = pg.PlotWidget()
        self.top_dock.setWidget(self.top_plot)
        # self.top_plot.setSizeHint(700, 200)
        self.addDockWidget(Qt.TopDockWidgetArea, self.top_dock)
        # self.top_dock.setSizePolicy(QSizePolicy.Minimum, QSizePolicy.Minimum)

        self.left_dock = QDockWidget("Left Dock", self)
        self.left_plot = pg.PlotWidget()
        self.left_dock.setWidget(self.left_plot)
        self.addDockWidget(Qt.LeftDockWidgetArea, self.left_dock)

        self.info_dock = QDockWidget("Info", self)
        info_widget = QFrame()
        info_widget.setLayout(QVBoxLayout())
        self.info_dock.setWidget(info_widget)
        self.addDockWidget(Qt.TopDockWidgetArea, self.info_dock)
        # self.info_dock.setSizePolicy(QSizePolicy.Minimum, QSizePolicy.Minimum)

        hist_dock = QDockWidget("hist", self)
        self.hist = pg.HistogramLUTWidget(image=self.image_view.image)
        # hist_dock.setWidget(self.hist)
        self.image_view.menu
        self.hist.setLevels(0, 512)
        self.hist.item.gradient.loadPreset("magma")
        self.addDockWidget(Qt.RightDockWidgetArea, hist_dock)

    def check_fit_state(self):
        self.fitting = self.fit_check.isChecked()

    def data_changed(self, value, metadata, persist, mods):
        try:
            img = value[self.args.img]
        except KeyError:
            return
        self.image_view.data_changed(value, metadata, persist, mods)
        self.top_plot.plotItem.clear()
        self.left_plot.plotItem.clear()
        slice_x = np.sum(img, axis=1)
        slice_y = np.sum(img, axis=0)
        self.top_plot.plot(slice_x)
        self.left_plot.plot(slice_y, np.arange(len(slice_y)))
        self.left_plot.invertX(True)

        if self.fitting:
            fit_x = fit_slice(slice_x)
            self.top_plot.plot(fit_x)
            fit_y = fit_slice(slice_y)
            self.left_plot.plot(fit_y, np.arange(len(slice_y)))


def fit_slice(slice_i):
    x_pixels = np.arange(len(slice_i))
    p0 = [np.argmax(slice_i), len(slice_i) / 10, max(slice_i), min(slice_i)]
    bounds = [
        (0, len(slice_i)),
        (0, len(slice_i)),
        (0, 2 * p0[0]),
        (-max(slice_i), max(slice_i)),
    ]
    bounds = [
        (0, 0, 0, -max(slice_i)),
        (len(slice_i), len(slice_i), 2 * p0[2], max(slice_i)),
    ]
    try:
        p, cov = curve_fit(gaussian, x_pixels, slice_i, p0=p0, bounds=bounds)
        fit = gaussian(x_pixels, *p)
    except RuntimeError:
        print("bad fit")
        fit = None
    return fit


def gaussian(x, mu, sigma, A, c):
    return A * np.exp(-((x - mu) ** 2 / (2 * sigma**2))) + c


def main():
    applet = SimpleApplet(ImageViewerWithSlices)
    applet.add_dataset("img", "image data (2D numpy array)")
    applet.run()


if __name__ == "__main__":
    main()
