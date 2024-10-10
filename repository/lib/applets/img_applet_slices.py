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
        self.initUI()
        self.fitting = False

    def initUI(self):

        self.setCentralWidget(self.image_view)
        self.createDockWidgets()
        # self.image.setSizePolicy(QSizePolicy.Minimum,QSizePolicy.Expanding)
        # self.setSizePolicy(QSizePolicy.Minimum,QSizePolicy.Expanding)
        # self.linedock.setMaximumWidth(100)
        # self.linedock.setMaximumHeight(100)
        # Qt.QTimer.singleShot(1000,self.res)

    def createDockWidgets(self):

        settings_dock = QDockWidget("Settings", self)
        settings_layout = QVBoxLayout()
        settings_widget = QFrame()
        settings_widget.setLayout(settings_layout)
        settings_dock.setWidget(settings_widget)
        self.addDockWidget(Qt.TopDockWidgetArea, settings_dock)
        settings_dock.setSizePolicy(QSizePolicy.Minimum, QSizePolicy.Minimum)
        self.fit_check = QCheckBox("Gauss fit?")
        settings_layout.addWidget(self.fit_check)
        self.fit_check.stateChanged.connect(self.check_fit_state)

        top_dock = QDockWidget()
        self.top_plot = pg.PlotWidget()
        top_dock.setWidget(self.top_plot)
        # self.top_plot.setSizeHint(700, 200)
        self.addDockWidget(Qt.TopDockWidgetArea, top_dock)
        top_dock.setSizePolicy(QSizePolicy.Minimum, QSizePolicy.Minimum)

        left_dock = QDockWidget()
        self.left_plot = pg.PlotWidget()
        left_dock.setWidget(self.left_plot)
        self.addDockWidget(Qt.LeftDockWidgetArea, left_dock)

        info_dock = QDockWidget("Info", self)
        info_widget = QFrame()
        info_widget.setLayout(QVBoxLayout())
        info_dock.setWidget(info_widget)
        self.addDockWidget(Qt.TopDockWidgetArea, info_dock)
        info_dock.setSizePolicy(QSizePolicy.Minimum, QSizePolicy.Minimum)

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
            fit_slice(slice_x, self.top_plot)
            fit_slice(slice_y, self.left_plot)


def fit_slice(slice_i, plot):
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
    p, cov = curve_fit(gaussian, x_pixels, slice_i, p0=p0, bounds=bounds)
    fit = gaussian(x_pixels, *p)
    return fit


def gaussian(x, mu, sigma, A, c):
    return A * np.exp(-((x - mu) ** 2 / (2 * sigma**2))) + c


def main():
    applet = SimpleApplet(ImageViewerWithSlices)
    applet.add_dataset("img", "image data (2D numpy array)")
    applet.run()


if __name__ == "__main__":
    main()
