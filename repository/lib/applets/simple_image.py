import numpy as np
import pyqtgraph
import pyqtgraph as pg
from artiq.applets.simple import SimpleApplet
from PyQt5 import QtCore
from PyQt5.QtWidgets import QLabel

# class ImageApplet(QWidget):
#     def __init__(self, args, req):
#         self.args = args
#         print("Initialising image applet")
#         super().__init__(self)
#         self.graphics_view = pg.GraphicsLayoutWidget()
#         plot = self.win.addPlot()
#         plot.setLabel("left", text="y", units="pixels")
#         plot.setLabel("bottom", text="x", units="pixels")
#         imgdata = np.ones([100, 100])
#         self.image_item = pg.ImageItem(imgdata)
#         self.invert_colors = False

#     def init_plot(self):
#         self.plot = self.graphics_view.addPlot()
#         self.plot.setLabel("left", text="y", units="m")
#         self.plot.setLabel("bottom", text="x", units="m")
#         colors = np.array(plt.cm.magma.colors) * 255
#         if self._invert_colors:
#             colors = colors[::-1]
#         cmap = pg.ColorMap(pos=np.linspace(0.0, 1.0, len(colors)), color=colors)
#         self.image_item.setLookupTable(cmap.getLookupTable())

#     def data_changed(self, value, metadata, persist, mods):
#         print("data changed")
#         try:
#             img = value[self.args.img]
#         except KeyError:
#             return
#         self.imgdata.setImage(img)


class SimpleImageViewer(pyqtgraph.ImageView):
    def __init__(self, args, req):
        super().__init__()
        self.args = args
        # Create two LineSegmentROI objects for the horizontal and vertical lines
        # Add the crosshair lines to the ImageView
        self.crosshair = pg.CrosshairROI(
            resizable=False, rotatable=False, movable=False
        )
        self.addItem(self.crosshair)
        self.getView().scene().sigMouseClicked.connect(self.mouseClicked)
        self.cursor_pos_label = QLabel("0.00, 0.00", self.ui.graphicsView.viewport())
        self.cursor_pos_label.setStyleSheet("background-color: white;")

        self.cursor_pos_label.setFixedSize(100, 20)
        self.cursor_pos_label.move(0, 0)

    def data_changed(self, value, metadata, persist, mods):
        try:
            img = value[self.args.img]
            size_x, size_y = [i / 20 for i in np.shape(img)]
        except KeyError:
            return
        self.setImage(img, autoRange=False, autoLevels=False)
        self.crosshair.setSize([size_x, size_y])

    # Update the crosshair position on mouse click
    def mouseClicked(self, evt):
        # Check if the left mouse button was clicked
        if evt.button() == QtCore.Qt.MouseButton.LeftButton:
            pos = evt.scenePos()  # Get the scene position where the click occurred
            if self.view.contains(pos):  # Check if the click is within the image view
                mouse_point = self.getView().mapSceneToView(pos)
                self.crosshair.setPos(mouse_point.x(), mouse_point.y())
                self.cursor_pos_label.setText(
                    f"{mouse_point.x():.2f}, {mouse_point.y():.2f}"
                )


def main():
    applet = SimpleApplet(SimpleImageViewer)
    applet.add_dataset("img", "image data (2D numpy array)")
    applet.run()


if __name__ == "__main__":
    main()
