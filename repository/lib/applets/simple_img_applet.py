from PyQt5 import QtCore
from PyQt5.QtWidgets import QLabel
import pyqtgraph as pg
import pyqtgraph
import numpy as np
from artiq.applets.simple import SimpleApplet


class SimpleImageViewer(pyqtgraph.ImageView):
    def __init__(self, args, req):
        super().__init__(view=pg.PlotItem())
        self.args = args
        # Create two LineSegmentROI objects for the horizontal and vertical lines
        # Add the crosshair lines to the ImageView
        self.crosshair = pg.CrosshairROI(
            pos=(0, 100), resizable=False, rotatable=False, movable=False
        )
        self.addItem(self.crosshair)
        self.getView().scene().sigMouseClicked.connect(self.mouseClicked)
        self.cursor_pos_label = QLabel("0.00, 0.00", self.ui.graphicsView.viewport())
        self.cursor_pos_label.setStyleSheet("background-color: white;")

        self.cursor_pos_label.setFixedSize(100, 20)
        self.cursor_pos_label.move(0, 0)
        self.getView().invertY(True)

    def data_changed(self, value, metadata, persist, mods):
        try:
            img = value[self.args.img]

            size_x, size_y = [i / 20 for i in np.shape(img)]
        except KeyError:
            return
        # self.ui.graphicsView.scale(1, -1)
        self.setImage(img, autoRange=False, autoLevels=False)
        self.getView().invertY(True)
        self.crosshair.setSize([size_x, size_y])

    # Update the crosshair position on mouse click
    def mouseClicked(self, evt):
        # Check if the left mouse button was clicked
        if evt.button() == QtCore.Qt.MouseButton.LeftButton:
            pos = evt.scenePos()  # Get the scene position where the click occurred
            if self.view.contains(pos):  # Check if the click is within the image view
                mouse_point = self.getView().getViewBox().mapSceneToView(pos)
                self.crosshair.setPos(mouse_point.x(), mouse_point.y())
                self.cursor_pos_label.setText(
                    f"{mouse_point.x():.2f}, {self.getImageItem().height() - mouse_point.y():.2f}"
                )


def main():
    applet = SimpleApplet(SimpleImageViewer)
    applet.add_dataset("img", "image data (2D numpy array)")
    applet.run()


if __name__ == "__main__":
    main()
