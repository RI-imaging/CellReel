import numpy as np
import pyqtgraph as pg


class CrossHairTwin(object):
    def __init__(self, plot1, plot2, callback):
        self.plots = [plot1, plot2]
        self.callback = callback

        self.vLine1 = pg.InfiniteLine(angle=90, movable=False)
        self.hLine1 = pg.InfiniteLine(angle=0, movable=False)
        self.vLine2 = pg.InfiniteLine(angle=90, movable=False)
        self.hLine2 = pg.InfiniteLine(angle=0, movable=False)

        plot1.addItem(self.vLine1, ignoreBounds=True)
        plot1.addItem(self.hLine1, ignoreBounds=True)

        plot2.addItem(self.vLine2, ignoreBounds=True)
        plot2.addItem(self.hLine2, ignoreBounds=True)

        plot1.scene.sigMouseMoved.connect(self.mouseMoved)
        plot2.scene.sigMouseMoved.connect(self.mouseMoved)

    def mouseMoved(self, evt):
        pos = evt
        for plot in self.plots:
            if plot.view.sceneBoundingRect().contains(pos):
                mousePoint = plot.getView().mapSceneToView(pos)
                x = int(np.floor(mousePoint.x()))
                y = int(np.floor(mousePoint.y()))
                # show at center of pixel to avoid ambiguities
                self.vLine1.setPos(x + .5)
                self.hLine1.setPos(y + .5)
                self.vLine2.setPos(x + .5)
                self.hLine2.setPos(y + .5)

                if self.plots[0].image is not None:
                    image1 = self.plots[0].image.T
                    shx, shy = image1.shape
                else:
                    image1 = None
                if self.plots[1].image is not None:
                    image2 = self.plots[1].image.T
                    shx, shy = image1.shape
                else:
                    image2 = None

                ri = np.nan
                fl = np.nan
                if x >= 0 and x < shx and y >= 0 and y < shy:
                    if image1 is not None:
                        ri = image1[x, y]
                    if image2 is not None:
                        fl = image2[x, y]

                self.callback(ri, fl)
