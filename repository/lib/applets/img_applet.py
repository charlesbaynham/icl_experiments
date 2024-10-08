from PyQt5 import QtGui, QtCore
from PyQt5.QtWidgets import QVBoxLayout, QWidget, QPushButton, QDialog
from PyQt5.QtCore import Qt
import PyQt5
import pyqtgraph as pg
import numpy as np
from artiq.applets.simple import SimpleApplet
import matplotlib.pyplot as plt


class ImageApplet(QWidget):
    def __init__(self):
        super().__init__(self)
        self.graphics_view = pg.GraphicsLayoutWidget()
        plot = self.win.addPlot()
        plot.setLabel("left", text="y", units="pixels")
        plot.setLabel("bottom", text="x", units="pixels")
        imgdata = np.ones([100, 100])
        self.image_item = pg.ImageItem(imgdata)
        self.invert_colors = False

    def init_plot(self):
        self.plot = self.graphics_view.addPlot()
        self.plot.setLabel("left", text="y", units="m")
        self.plot.setLabel("bottom", text="x", units="m")
        colors = np.array(plt.cm.magma.colors) * 255
        if self._invert_colors:
            colors = colors[::-1]
        cmap = pg.ColorMap(pos=np.linspace(0.0, 1.0, len(colors)), color=colors)
        self.image_item.setLookupTable(cmap.getLookupTable())

    def data_changed(self, value, metadata, persist, mods):
        try:
            img = value[self.args.img]
        except KeyError:
            return
        self.imgdata.setImage(img)


def main():
    applet = SimpleApplet(ImageApplet)
    applet.add_dataset("img", "image data (2D numpy array)")
    applet.run()


if __name__ == "__main__":
    main()
