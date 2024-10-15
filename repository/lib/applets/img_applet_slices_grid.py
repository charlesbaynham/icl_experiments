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
    QGridLayout,
    QLabel,
    QGraphicsProxyWidget,
    QSplitter,
    QHBoxLayout,
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


class ImageViewerWithSlicesGrid(QMainWindow):
    def __init__(self, args, req):
        super().__init__()
        self.args = args
        self.req = req
        # Create central widget for the layout
        self.init_ui()
        self.fitting = False

    def init_ui(self):

        # Create central widget for the main window
        self.central_widget = QWidget(self)
        self.setCentralWidget(self.central_widget)
        # Create a QGridLayout
        self.grid_layout = QGridLayout(self.central_widget)
        # 1. Create central plot item (PlotItem is embedded in a PlotWidget)
        self.image_item = pg.ImageItem()
        self.image_item.setImage(np.zeros([100, 100]))
        self.central_plot = pg.PlotWidget()
        self.central_plot.addItem(self.image_item)

        self.grid_layout.addWidget(self.central_plot, 1, 1)

        # 2. Create top plot (same width as central plot)
        self.top_plot = pg.PlotWidget()
        self.grid_layout.addWidget(self.top_plot, 0, 1)

        # 3. Create left plot (same height as central plot)
        self.left_plot = pg.PlotWidget()
        self.grid_layout.addWidget(self.left_plot, 1, 0)

        # 4. Create the HistogramLUTWidget on the right
        self.right_area = QWidget()
        self.right_layout = QVBoxLayout()
        self.right_area.setLayout(self.right_layout)
        self.hist_lut = pg.HistogramLUTWidget()
        self.hist_lut.setImageItem(self.image_item)
        self.right_layout.addWidget(self.hist_lut)
        self.right_layout.addWidget(self.create_settings_box())

        self.grid_layout.addWidget(self.right_area, 1, 2)

        self.create_info_boxes()

        # Set the fixed height for the top plot and fixed width for the left plot
        self.top_plot.setFixedHeight(120)  # Adjust this as needed
        self.left_plot.setFixedWidth(120)  # Adjust this as needed
        self.hist_lut.setFixedWidth(100)

        # Set stretch factors so that only the central plot expands
        self.grid_layout.setColumnStretch(1, 1)  # Central plot column stretches
        self.grid_layout.setColumnStretch(0, 0)  # Left plot column stays fixed
        self.grid_layout.setColumnStretch(2, 0)  # HistogramLUTWidget stays fixed width

        self.grid_layout.setRowStretch(1, 1)  # Central plot row stretches
        self.grid_layout.setRowStretch(0, 0)  # Top plot row stays fixed height

        # Set some initial window properties
        self.setGeometry(100, 100, 1000, 600)

        self.create_crosshair()

    def create_crosshair(self):
        self.crosshair = pg.CrosshairROI(
            pos=(0, 0), resizable=False, rotatable=False, movable=False
        )
        self.central_plot.addItem(self.crosshair)
        self.central_plot.scene().sigMouseClicked.connect(self.mouseClicked)
        self.cursor_pos_label = QLabel("x: 0.00, y: 0.00: A: 0.00", self.central_plot)
        self.cursor_pos_label.setStyleSheet("background-color: white;")

        self.cursor_pos_label.setFixedSize(220, 20)
        self.cursor_pos_label.move(0, 0)

        return self.crosshair

    def create_settings_box(self):
        self.settings_box = QFrame()
        self.settings_layout = QHBoxLayout()
        self.settings_layout.setContentsMargins(
            0, 0, 0, 0
        )  # No margins around the layout
        self.settings_layout.setSpacing(0)  # 5-pixel spacing between widgets
        self.settings_box.setLayout(self.settings_layout)

        self.roi_button = QPushButton()
        self.roi_button.setText("ROI")
        self.roi_button.setFixedWidth(40)
        self.roi_button.setCheckable(True)
        self.settings_layout.addWidget(self.roi_button)
        self.create_roi()
        self.roi_button.clicked.connect(self.roi_pressed)

        self.fit_button = QPushButton()
        self.fit_button.setText("Fit")
        self.fit_button.setFixedWidth(40)
        self.fit_button.setCheckable(True)
        self.settings_layout.addWidget(self.fit_button)

        return self.settings_box

    def create_info_boxes(self):
        self.fit_result_x = FitResultFrame()
        self.fit_result_y = FitResultFrame()
        self.grid_layout.addWidget(self.fit_result_x, 0, 2)
        self.grid_layout.addWidget(self.fit_result_y, 0, 0)

        self.fit_result_x_roi = FitResultFrame()
        self.fit_result_y_roi = FitResultFrame()
        self.grid_layout.addWidget(self.fit_result_x_roi, 2, 2)
        self.grid_layout.addWidget(self.fit_result_y_roi, 2, 0)
        self.fit_result_x_roi.hide()
        self.fit_result_y_roi.hide()

    def create_roi(self):
        self.roi = pg.RectROI((0, 0), size=pg.Point(10, 10))
        self.roi.addRotateHandle([1, 0], [0.5, 0.5])  # Adding a rotation handle
        self.roi.addScaleHandle([1, 1], [0, 0])  # Adding a scale handle
        self.central_plot.addItem(self.roi)

        self.roi_plot_splitter = QSplitter(Qt.Horizontal)
        self.roi_plot_1 = ROIPlot(self.roi, self.image_item)
        self.roi_plot_2 = ROIPlot(self.roi, self.image_item, axis=1)
        self.roi_plot_splitter.addWidget(self.roi_plot_1)
        self.roi_plot_splitter.addWidget(self.roi_plot_2)
        self.roi_plot_splitter.setMaximumHeight(100)
        self.grid_layout.addWidget(self.roi_plot_splitter, 2, 1)
        self.roi_plot_splitter.hide()

        self.x_line = pg.InfiniteLine(movable=True)
        self.y_line = pg.InfiniteLine(angle=0, movable=True)
        self.top_plot.addItem(self.x_line)
        self.left_plot.addItem(self.y_line)
        self.roi.hide()

        return self.roi

    def roi_pressed(self):
        checked = self.roi_button.isChecked()
        for widget in [
            self.roi,
            self.roi_plot_splitter,
            self.fit_result_x_roi,
            self.fit_result_y_roi,
        ]:
            widget.setVisible(checked)

    def data_changed(self, value, metadata, persist, mods):
        try:
            img = value[self.args.img]
        except KeyError:
            return
        # self.image_view.data_changed(value, metadata, persist, mods)
        self.image_item.setImage(img, autoRange=False, autoLevels=False)
        self.top_plot.clear()
        self.left_plot.clear()
        slice_x = np.sum(img, axis=1)
        slice_y = np.sum(img, axis=0)
        self.top_plot.plot(slice_x)
        self.top_plot.addItem(self.x_line)
        self.left_plot.plot(slice_y, np.arange(len(slice_y)))
        self.left_plot.invertX(True)
        self.left_plot.addItem(self.y_line)

        if self.fit_button.isChecked():
            fit_x, p_x = fit_slice(slice_x)

            fit_y, p_y = fit_slice(slice_y)
            if fit_x is not None:
                self.top_plot.plot(fit_x)
                self.fit_result_x.set_labels(p_x)
            if fit_y is not None:
                self.left_plot.plot(fit_y, np.arange(len(slice_y)))

            self.fit_result_x.set_labels(p_x)
            self.fit_result_y.set_labels(p_y)

            if self.roi_button.isChecked():
                fit_roi_x, p_roi_x = fit_slice(self.roi_plot_1.getRoiData())
                fit_roi_y, p_roi_y = fit_slice(self.roi_plot_2.getRoiData())
                self.roi_plot_1.roiChangedEvent()
                self.roi_plot_2.roiChangedEvent()
                if fit_roi_x is not None:
                    self.roi_plot_1.plotItem.plot(fit_roi_x)
                    self.fit_result_x_roi.set_labels(p_roi_x)
                if fit_roi_y is not None:
                    self.roi_plot_2.plotItem.plot(fit_roi_y)
                    self.fit_result_y_roi.set_labels(p_roi_y)

    def update_crosshair(self, mouse_point):
        if self.central_plot.viewRect().contains(mouse_point):
            # Check if the click is within the image view
            self.crosshair.setPos(mouse_point.x(), mouse_point.y())
            A = self.image_item.image[int(mouse_point.x()), int(mouse_point.y())]
            self.cursor_pos_label.setText(
                f"x: {mouse_point.x():.2f}, y: {mouse_point.y():.2f}, A: {A:.2f}"
            )
            self.x_line.setPos(mouse_point.x())
            self.y_line.setPos(mouse_point.y())

    # Update the crosshair position on mouse click
    def mouseClicked(self, evt):
        # Check if the left mouse button was clicked
        if evt.button() == QtCore.Qt.MouseButton.LeftButton:
            pos = evt.scenePos()  # Get the scene position where the click occurred
            mouse_point = self.central_plot.plotItem.vb.mapSceneToView(pos)
            self.update_crosshair(mouse_point)


class FitResultFrame(QFrame):
    def __init__(self):
        super().__init__()
        self.layout = QVBoxLayout()
        self.mu_label = QLabel("mu: None")
        self.mu_label.setFont(QtGui.QFont("Arial", 10))
        self.layout.addWidget(self.mu_label)
        self.sig_label = QLabel("sig: None")
        self.sig_label.setFont(QtGui.QFont("Arial", 10))
        self.layout.addWidget(self.sig_label)
        self.A_label = QLabel("A: None")
        self.A_label.setFont(QtGui.QFont("Arial", 10))
        self.layout.addWidget(self.A_label)
        self.c_label = QLabel("c: None")
        self.c_label.setFont(QtGui.QFont("Arial", 10))
        self.layout.addWidget(self.c_label)
        self.setLayout(self.layout)

    def set_labels(self, p):
        if p[0] is not None:
            self.mu_label.setText(f"mu: {p[0]:.2f}")
            self.sig_label.setText(f"sig: {p[1]:.2f}")
            self.A_label.setText(f"A: {p[2]:.2f}")
            self.c_label.setText(f"c: {p[3]:.2f}")
        else:
            self.mu_label.setText("mu: None")
            self.sig_label.setText("sig: None")
            self.A_label.setText("A: None")
            self.c_label.setText("c: None")


class ROIPlot(pg.PlotWidget):
    """Plot curve that monitors an ROI and image for changes to automatically replot."""

    def __init__(
        self,
        roi: pg.ROI,
        img: pg.ImageItem,
        axes=(0, 1),
        xVals=None,
        color=None,
        axis=0,
    ):
        self.roi = roi
        self.image_item = img
        self.axes = axes
        self.xVals = xVals
        self.axis = axis
        super().__init__()
        # roi.connect(roi, QtCore.SIGNAL('regionChanged'), self.roiChangedEvent)
        roi.sigRegionChanged.connect(self.roiChangedEvent)
        # self.roiChangedEvent()

    def getRoiData(self):
        d = self.roi.getArrayRegion(
            self.image_item.image, self.image_item, axes=self.axes
        )
        if d is None:
            return
        while d.ndim > 1:
            d = d.mean(axis=self.axis)
        return d

    def roiChangedEvent(self):
        self.plotItem.clear()
        d = self.getRoiData()
        self.plot(d)


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
    except (RuntimeError, ValueError):
        fit = None
        p = [None] * 4
    return fit, p


def gaussian(x, mu, sigma, A, c):
    return A * np.exp(-((x - mu) ** 2 / (2 * sigma**2))) + c


def main():
    applet = SimpleApplet(ImageViewerWithSlicesGrid)
    applet.add_dataset("img", "image data (2D numpy array)")
    applet.run()


if __name__ == "__main__":
    main()
